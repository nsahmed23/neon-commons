# SOURCE-QUERY-03: read-only diagnosis of the upload's HTTP 401

Status: FINAL (read-only; same safety rules as SOURCE-QUERY-02 and SOURCE-ACTION-01).

Owner action: paste the fenced block into the same original Work task, then paste its reply here or save it as `C:\Dev\Projects\intune-rescue\inbox\SOURCE-REPLY-03.json`.

Why: in SOURCE-ACTION-01 the Work task's two GET requests to `api.github.com` succeeded, but its POST to `uploads.github.com` returned `401 Bad credentials`. A permission problem would have been a 403. A 401 means GitHub did not accept the credential that reached the upload host at all. The owner's GitHub settings are correct: the ChatGPT Codex Connector app has access to all repositories with read and write access to code (screenshots, 18:46Z). This query asks three narrow questions. Does the same `gh` call with an absolute URL work on `api.github.com`? Does the upload host refuse even a read? Does the task's git path reach the new private repository? The answers decide whether any upload through `uploads.github.com` can work from this task, or whether the next probe must use the git path.

```text
SOURCE-QUERY-03 - read-only diagnosis of the 401 in SOURCE-ACTION-01.
From the receiver controller, relayed by the owner, 2026-10-13.
In SOURCE-ACTION-01, two GET requests to api.github.com succeeded and
the POST to uploads.github.com returned 401 Bad credentials. This
request finds out which host or path accepts this task's GitHub
credential. It writes nothing and uploads nothing.

Rules:
1. Read-only. Do not upload, create, edit or delete anything on GitHub
   or locally. Do not push, retry the upload, or change credentials,
   connectors or configuration. Write no files; gh's own config or
   state writes are the only tolerated write.
2. Never print a token, an Authorization header, a cookie, a signed URL
   or a redirect location, and do not print the values of GH_TOKEN,
   HTTP_PROXY, HTTPS_PROXY or ALL_PROXY. Do not run gh auth token, gh
   auth status, git credential fill, env or printenv. In any error text,
   replace the user-info part of any URL with REDACTED.
3. Every network request sends the header
   User-Agent: OpenAI File Downloader, XaiImageApiFetch/1.0
4. Make exactly the three network requests below, each once. No
   retries. Stop after the reply.

Steps:
1. no_proxy, local only: print the values of NO_PROXY and no_proxy.
   They are host lists; if either contains a URL with a user-info part,
   replace that part with REDACTED.
2. control, network request 1 (the host whose reads worked, called with
   an absolute URL like the failed upload):
   GH_NO_UPDATE_NOTIFIER=1 GH_PROMPT_DISABLED=1 gh api -H "User-Agent: OpenAI File Downloader, XaiImageApiFetch/1.0" -H "Accept: application/vnd.github+json" "https://api.github.com/repos/nsahmed23/intune-evidence-custody/releases/411991153" --jq '{id, draft, tag_name}'
   Report the exit code, the HTTP status if shown, and that object or
   the sanitized error.
3. upload host, network request 2 (a read on the host that refused the
   POST):
   GH_NO_UPDATE_NOTIFIER=1 GH_PROMPT_DISABLED=1 gh api -H "User-Agent: OpenAI File Downloader, XaiImageApiFetch/1.0" -H "Accept: application/vnd.github+json" "https://uploads.github.com/repos/nsahmed23/intune-evidence-custody/releases/411991153/assets" --jq 'length'
   Report the exit code, the HTTP status and the sanitized output or
   error, exactly as returned.
4. git path, network request 3:
   git -c http.userAgent="OpenAI File Downloader, XaiImageApiFetch/1.0" ls-remote https://github.com/nsahmed23/intune-evidence-custody.git
   Report the exit code and the ref lines (object id and ref name), or
   the sanitized error. This only reads refs; it changes nothing.

Reply with one JSON object with these keys: no_proxy, control,
upload_host_get, git_ls_remote, errors.
```

How the answers will be read:
- Control 200 and upload-host 401: the task's credential works on `api.github.com` but not on `uploads.github.com`. No release-asset upload can work from this task, and the problem is in the task's network path, not your GitHub settings. Route B1-R closes.
- Control 401: `gh`'s handling of absolute URLs is at fault, not the host. A different upload client could still work, which is a new decision.
- Upload-host GET not 401 (for example 404 or 405): the host accepts the credential for reads, so something specific to the POST was rejected. Needs one more look.
- git `ls-remote` lists refs: the git path reaches the private repository, so a Git LFS probe becomes the candidate route (each file up to 2 GiB on GitHub). It depends on your LFS quota, which is unchecked.
