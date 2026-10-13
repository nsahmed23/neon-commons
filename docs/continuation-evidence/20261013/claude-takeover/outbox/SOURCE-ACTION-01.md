# SOURCE-ACTION-01: upload the synthetic probe to the approved draft release

Status: FINAL. Reviewed by Fable 5.1 (R22: SEND, no blocking items; all three optional hardenings applied: no gh update check, the exact app to grant, and sanitized proxy errors). The controller added a read-only privacy check of the destination before any write. Use only after the owner has done all three steps of OA-2. First, create the private repository with a README. Second, create a draft release tagged `probe-20261013-01` with no files. Third, send the approval line in `outbox/ROUTE-DECISION-01.md`.

Owner action: if you named the repository something other than `intune-evidence-custody`, replace that name in the four places it appears below. Then paste the fenced block into the same original Work task. Paste its reply here, or save it as `C:\Dev\Projects\intune-rescue\inbox\SOURCE-ACTION-REPLY-01.json`. Then download the asset from the draft release page in your browser into a new empty folder, and tell Claude the path.

What this tests: route B1-R end to end on 18,445 synthetic bytes. The source's own GitHub credential writes a release asset to a private repository, then you download it and Claude compares the hash. A pass does not cover a 1.47 GB upload or any evidence classification.

```text
SOURCE-ACTION-01 - one approved synthetic upload, relayed by the owner, 2026-10-13.
Authority: the owner approved route B1-R for the synthetic probe only:
private repository nsahmed23/intune-evidence-custody, draft release tagged
probe-20261013-01. This action makes exactly three network requests:
read the repository's visibility, list its releases, then upload one
file to that draft release.

Rules:
1. Upload only the file
   /workspace/intune-synthetic-export-work-export-b3071470-cc42-454e-876c-3e6a189e5beb/synthetic-original-work-probe.zip
   as one asset of that draft. Upload, export or send nothing else.
   Apart from adding that one asset, do not create, edit, publish or
   delete any release, tag, branch, commit or repository, and do not
   push. Do not touch nsahmed23/neon-commons. Do not change credentials,
   connectors, approvals or configuration. Write no files; gh's own
   config or state writes are the only tolerated write.
2. Never print a token, an Authorization header, a signed URL or a
   redirect location. In any error text, replace the user-info part of
   any URL with REDACTED. Use gh's own authentication as it is. Do not
   run gh auth token, gh auth status, git credential fill, env or
   printenv.
3. All three requests must send the header
   User-Agent: OpenAI File Downloader, XaiImageApiFetch/1.0
   If the client cannot send it, stop and report.
4. No retries. A non-zero exit or any HTTP error stops the action; report
   the exit code and the sanitized error message as they are. A
   connection or proxy error with no HTTP status means the host is not
   reachable through the proxy: report it as ROUTE_UNREACHABLE, not as
   an authentication failure.
5. Stop after the reply.

Steps:
1. preflight, local only: size and SHA-256 of the probe file, with size
   and mtime before and after hashing. Continue only if it is 18445
   bytes with SHA-256
   d01a9b0e9cd1506b1ee5d0defcfebf4f377af858ab610d3ec5362623ee0c67c3
   and size and mtime did not change.
2. destination check, network request 1:
   GH_NO_UPDATE_NOTIFIER=1 GH_PROMPT_DISABLED=1 gh api -H "User-Agent: OpenAI File Downloader, XaiImageApiFetch/1.0" -H "Accept: application/vnd.github+json" repos/nsahmed23/intune-evidence-custody --jq '{full_name, private, visibility}'
   Continue only if private is true. Report the exit code and that
   object.
3. release lookup, network request 2:
   GH_NO_UPDATE_NOTIFIER=1 GH_PROMPT_DISABLED=1 gh api -H "User-Agent: OpenAI File Downloader, XaiImageApiFetch/1.0" -H "Accept: application/vnd.github+json" repos/nsahmed23/intune-evidence-custody/releases --jq '[.[] | select(.tag_name == "probe-20261013-01") | {id, draft, tag_name, asset_names: [.assets[].name]}]'
   Continue only if exactly one release matches, with draft true and no
   assets. Report the exit code and that object.
4. upload, network request 3, using the id from step 3:
   GH_NO_UPDATE_NOTIFIER=1 GH_PROMPT_DISABLED=1 gh api --method POST -H "User-Agent: OpenAI File Downloader, XaiImageApiFetch/1.0" -H "Content-Type: application/zip" "https://uploads.github.com/repos/nsahmed23/intune-evidence-custody/releases/<id>/assets?name=synthetic-original-work-probe.zip" --input /workspace/intune-synthetic-export-work-export-b3071470-cc42-454e-876c-3e6a189e5beb/synthetic-original-work-probe.zip --jq '{id, name, size, state, content_type}'
   Report the exit code and that object. A good result has name
   synthetic-original-work-probe.zip, size 18445 and state uploaded.

Reply with one JSON object with these keys: preflight, destination,
release_lookup, upload, errors.
```
