/* Literal local TLS acceptance client. Not the Intune provider or live evidence. */
#include <arpa/inet.h>
#include <openssl/ssl.h>
#include <openssl/x509v3.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>

static void die(const char *message) { fprintf(stderr, "%s\n", message); exit(2); }
static int request(const char *host, const char *message, char *reply, size_t cap) {
    int fd = socket(AF_INET, SOCK_STREAM, 0);
    struct sockaddr_in addr = {.sin_family = AF_INET, .sin_port = htons(18080)};
    inet_pton(AF_INET, "127.0.0.1", &addr.sin_addr);
    if (fd < 0 || connect(fd, (struct sockaddr *)&addr, sizeof(addr))) die("relay-connect");
    char tunnel[512], head[2048]; size_t used = 0;
    int count = snprintf(tunnel, sizeof(tunnel), "CONNECT %s:443 HTTP/1.1\r\nHost: %s:443\r\n\r\n", host, host);
    if (write(fd, tunnel, count) != count) die("connect-write");
    while (used + 1 < sizeof(head)) {
        if (read(fd, head + used, 1) != 1) die("connect-read");
        used++; head[used] = 0;
        if (used >= 4 && !memcmp(head + used - 4, "\r\n\r\n", 4)) break;
    }
    if (strncmp(head, "HTTP/1.1 200 ", 13)) die("connect-rejected");
    SSL_CTX *ctx = SSL_CTX_new(TLS_client_method());
    if (!ctx || SSL_CTX_set_min_proto_version(ctx, TLS1_2_VERSION) != 1 ||
        SSL_CTX_load_verify_locations(ctx, "/control/broker-ca.pem", NULL) != 1) die("tls-context");
    SSL_CTX_set_verify(ctx, SSL_VERIFY_PEER, NULL);
    SSL *ssl = SSL_new(ctx);
    if (!ssl || SSL_set_fd(ssl, fd) != 1 || SSL_set_tlsext_host_name(ssl, host) != 1 ||
        SSL_set1_host(ssl, host) != 1 || SSL_connect(ssl) != 1 || SSL_get_verify_result(ssl) != X509_V_OK) die("tls-verify");
    size_t length = strlen(message), sent = 0;
    while (sent < length) { int n = SSL_write(ssl, message + sent, length - sent); if (n <= 0) die("tls-write"); sent += n; }
    used = 0;
    while (used + 1 < cap) { int n = SSL_read(ssl, reply + used, cap - used - 1); if (n <= 0) break; used += n; }
    reply[used] = 0; SSL_free(ssl); SSL_CTX_free(ctx); close(fd);
    return !strncmp(reply, "HTTP/1.1 200 ", 13);
}
int main(int argc, char **argv) {
    (void)argv; if (argc != 1) die("no-arguments");
    const char *form = "client_id=00000000-0000-0000-0000-000000000002&client_secret=synthetic-secret&grant_type=client_credentials&scope=https%3A%2F%2Fgraph.microsoft.com%2F.default";
    char message[4096], reply[32768];
    snprintf(message, sizeof(message), "POST /00000000-0000-0000-0000-000000000001/oauth2/v2.0/token HTTP/1.1\r\nHost: login.fixture.invalid\r\nContent-Type: application/x-www-form-urlencoded\r\nContent-Length: %zu\r\n\r\n%s", strlen(form), form);
    if (!request("login.fixture.invalid", message, reply, sizeof(reply)) || !strstr(reply, "fixture-1")) die("oauth-fixture");
    const char *body = "{\"name\":\"exact approved correction\"}";
    snprintf(message, sizeof(message), "PUT /beta/deviceManagement/configurationPolicies/id HTTP/1.1\r\nHost: graph.fixture.invalid\r\nAuthorization: Bearer fixture-1\r\nContent-Type: application/json\r\nContent-Length: %zu\r\n\r\n%s", strlen(body), body);
    if (!request("graph.fixture.invalid", message, reply, sizeof(reply))) die("mutation-fixture");
    const char *readback = "GET /beta/deviceManagement/configurationPolicies/id HTTP/1.1\r\nHost: graph.fixture.invalid\r\nAuthorization: Bearer fixture-1\r\nContent-Length: 0\r\n\r\n";
    if (!request("graph.fixture.invalid", readback, reply, sizeof(reply)) || !strstr(reply, "{\"accepted\":true}")) die("readback-fixture");
    FILE *out = fopen("/job/literal-readback.txt", "wx");
    if (!out || fwrite(reply, 1, strlen(reply), out) != strlen(reply) || fclose(out)) die("readback-file");
    puts("NATIVE-CONTAINER-TLS-FIXTURE-COMPLETE"); return 0;
}
