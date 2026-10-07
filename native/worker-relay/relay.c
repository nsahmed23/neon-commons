/* Fixed laboratory-qualified worker proxy relay. No destination configuration.
 * The network-none host boundary is mandatory; this is not an authorization
 * broker. It carries opaque CONNECT/TLS bytes to the host policy broker. */
#define _GNU_SOURCE
#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <pthread.h>
#include <signal.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <time.h>
#include <unistd.h>
#include <string.h>

static pthread_mutex_t mutex = PTHREAD_MUTEX_INITIALIZER;
static unsigned active;
static volatile sig_atomic_t stopping;
static int listener = -1;
static void stop(int unused) { (void)unused; stopping = 1; if (listener >= 0) close(listener); }
static long long now_ms(void) {
    struct timespec t;
    if (clock_gettime(CLOCK_MONOTONIC, &t)) return -1;
    return (long long)t.tv_sec * 1000 + t.tv_nsec / 1000000;
}
static int send_bytes(int fd, const char *data, ssize_t length, long long deadline) {
    while (length > 0) {
        long long remaining = deadline - now_ms();
        if (remaining <= 0 || remaining > 20000) return -1;
        struct pollfd p = {fd, POLLOUT, 0};
        int result = poll(&p, 1, (int)remaining);
        if (result <= 0 || !(p.revents & POLLOUT)) return -1;
        ssize_t sent = send(fd, data, (size_t)length, MSG_NOSIGNAL);
        if (sent < 0 && (errno == EINTR || errno == EAGAIN)) continue;
        if (sent <= 0) return -1;
        data += sent; length -= sent;
    }
    return 0;
}
static void *relay(void *argument) {
    int client = (int)(intptr_t)argument, upstream = -1;
    long long deadline = now_ms() + 20000;
    upstream = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC | SOCK_NONBLOCK, 0);
    if (upstream < 0) goto done;
    struct sockaddr_un address = {0}; address.sun_family = AF_UNIX;
    memcpy(address.sun_path, "/broker/egress.sock", sizeof("/broker/egress.sock"));
    if (connect(upstream, (struct sockaddr *)&address, sizeof(address))) goto done;
    int descriptors[2] = {client, upstream};
    unsigned readable = 2;
    struct pollfd peers[2] = {{client, POLLIN, 0}, {upstream, POLLIN, 0}};
    size_t totals[2] = {0, 0};
    const size_t limits[2] = {2U * 1024U * 1024U, 18U * 1024U * 1024U};
    char buffer[16384];
    while (!stopping) {
        long long remaining = deadline - now_ms();
        if (remaining <= 0 || remaining > 20000) break;
        int result = poll(peers, 2, (int)remaining);
        if (result < 0 && errno == EINTR) continue;
        if (result <= 0) break;
        for (int i = 0; i < 2; ++i) {
            if (!(peers[i].revents & (POLLIN | POLLHUP | POLLERR | POLLNVAL))) continue;
            ssize_t count = recv(peers[i].fd, buffer, sizeof(buffer), 0);
            if (count < 0 && (errno == EINTR || errno == EAGAIN)) continue;
            if (count < 0) goto done;
            if (count == 0) {
                peers[i].fd = -1;
                if (shutdown(descriptors[1-i], SHUT_WR) && errno != ENOTCONN) goto done;
                if (--readable == 0) goto done;
                continue;
            }
            totals[i] += (size_t)count;
            if (totals[i] > limits[i] || send_bytes(descriptors[1-i], buffer, count, deadline)) goto done;
        }
    }
done:
    if (upstream >= 0) close(upstream);
    close(client);
    pthread_mutex_lock(&mutex); --active; pthread_mutex_unlock(&mutex);
    return NULL;
}
int main(int argc, char **argv) {
    (void)argv;
    if (argc != 1) return 64;
    signal(SIGPIPE, SIG_IGN); signal(SIGTERM, stop); signal(SIGINT, stop);
    listener = socket(AF_INET, SOCK_STREAM | SOCK_CLOEXEC, 0);
    if (listener < 0) return 70;
    struct sockaddr_in address = {0}; address.sin_family = AF_INET;
    address.sin_port = htons(18080); address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    if (bind(listener, (struct sockaddr *)&address, sizeof(address)) || listen(listener, 4)) return 71;
    int ready = open("/job/relay.ready", O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
    if (ready < 0) return 72;
    if (write(ready, "READY\n", 6) != 6 || fsync(ready) || close(ready)) return 73;
    while (!stopping) {
        int client = accept4(listener, NULL, NULL, SOCK_CLOEXEC | SOCK_NONBLOCK);
        if (client < 0) { if (errno == EINTR) continue; break; }
        pthread_mutex_lock(&mutex);
        if (active >= 4) { pthread_mutex_unlock(&mutex); close(client); continue; }
        ++active; pthread_mutex_unlock(&mutex);
        pthread_t thread;
        if (pthread_create(&thread, NULL, relay, (void *)(intptr_t)client)) {
            close(client); pthread_mutex_lock(&mutex); --active; pthread_mutex_unlock(&mutex);
        } else pthread_detach(thread);
    }
    return 0;
}
