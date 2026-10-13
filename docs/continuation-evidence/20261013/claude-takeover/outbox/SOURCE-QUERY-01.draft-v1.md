# SOURCE-QUERY-01: read-only inventory for the original ChatGPT Work task

Owner action: paste everything inside the fenced block below into the original ChatGPT Work task (the one holding `/workspace/intune-continuation`). Save its reply as `C:\Dev\Projects\intune-rescue\inbox\SOURCE-REPLY-01.json`, or paste the reply into the Claude Code session.

Why now: the four archive layers live only in that task's tmpfs. C32 records that earlier tmpfs originals vanished across a resumption, so every hour of delay risks the same loss. This request moves nothing; it rechecks availability and lists which export routes exist, so the next step can pick a route instead of guessing.

```text
SOURCE-QUERY-01 - read-only availability and export-capability inventory.
From the receiver controller, relayed by the owner, 2026-10-13.
Checkpoint: C32 commit d057cc15c9928dd1a34a965b8d8ebf8e6755d94a on branch
continuation/r4-20261007 (still the remote tip at 2026-10-13 14:45 UTC).

This request is read-only. It is not an export retry and not a transfer.

Rules:
1. Do not upload, export, attach, share, copy, move, rename, compress, split,
   delete, restore or retry anything. Do not change the repository,
   credentials, connectors, approvals or any laboratory state. Do not start
   background work.
2. Never print tokens, keys, cookies, signed URLs or private file contents.
   Paths, sizes, hashes, tool names and error strings are fine.
3. Do not create files (/workspace has about 3 MB free). Reply inline with
   one JSON object.
4. If a step fails or is unavailable, record the exact error or "UNKNOWN"
   and continue with the next step.
5. Stop after the reply.

Steps:
1. environment: current UTC time; whether this is the retained instance
   recorded in C32 (instance129, identity as118, uid 1000); boot time or
   uptime; whether any reset or resumption happened since
   2026-10-12T21:53Z.
2. archives: for each C32 snapshot layer give the exact current path, size
   in bytes and a freshly computed SHA-256, compared with these pins
   (label, bytes, sha256):
   r4-evidence                     1469518188  7bbc9f88eee9b4c417f622fb76cb5e2c0b0d4790d5b7cceaa2ae661ce2012ad7
   provider-candidates                9849950  755b9f4f8d29e562f476fc7e1f3bb8f376fd0fbfbeabe7a8e7e7ec78099280c7
   current-diagnostic-scratch        14485539  60960f3760f24893e7114185d5d14ee7ab3e35e1fc17008097d2b6eecc83e939
   current-exact-artifact-scratch    41538870  c221c1410d905806275dc3ea72c2793db83839816d112d4d3095e3bbe4819add
   manifests: same for each layer's manifest:
   r4-evidence                       35983862  9f53658f8b795e136d32baab6d7043741a81cd6450e9d640489fb01a97610fb1
   provider-candidates                2875760  bccf1c15dcda000ebeae37f1c23de016233d062d8a0edcf535b39f67ffd99fa6
   current-diagnostic-scratch            5496  43ef5e7852f9e2be9878cfc17ef096182d166fc693b970333828e54e11f7b992
   current-exact-artifact-scratch     1677589  5d8b84ecc1c8bf9690fa0cbfa0012650430e36f302f4982969a04366b7984c2e
   archive_format: the container format of the layers (for example tar,
   tar.zst, zip or custom) and the paths of the builder and restorer that
   wrote and read them.
3. probe: path, size and SHA-256 of synthetic-original-work-probe.zip
   (expected 18445 bytes,
   d01a9b0e9cd1506b1ee5d0defcfebf4f377af858ab610d3ec5362623ee0c67c3) and of
   WORK-EXPORT-PROBE.json (expected 2426 bytes).
4. capacity: free bytes and free inodes for /workspace and for the tmpfs
   holding the archives; total and available memory.
5. export_capabilities, listing only, invoke nothing:
   a. every tool or connector action exposed in this task that can deliver
      a file from this machine to the owner: chat attachment or download
      link, Library, Drive, GitHub, or anything else. For each: exact name,
      direction, documented size limit, and whether it accepts arbitrary
      binary files.
   b. github_mechanism: how the C32 publication to
      github.com/nsahmed23/neon-commons was performed (git CLI with a stored
      credential, gh CLI, or a connector action); whether that same
      mechanism can reach a private repository owned by nsahmed23; whether
      it can upload release assets or Git LFS objects. Use only read-only
      checks such as gh auth status or an API GET that shows granted
      scopes. Do not create repositories, branches, releases or pushes.
   c. drive_action: the exact Drive action name used in the failed probe
      and the OAuth scopes it holds, if visible without exposing token
      values.
6. writers: any running process that writes under
   /workspace/intune-continuation or the archive locations (PID and command
   name only). Do not stop anything.
7. post_cutoff_records: the snapshot cutoff timestamp you used, then the
   paths, sizes and modification times of records created after it under
   the evidence epoch (including the C32 final receipt,
   EXPORT-BOUNDARY-STOP.json and the export-probe records). List only.
8. retention: any documented or observed rule for how long /tmp and
   /workspace survive in this task (idle timeout, resumption, deletion).

Reply with one JSON object with these keys: environment, archives,
manifests, archive_format, probe, capacity, export_capabilities,
github_mechanism, drive_action, writers, post_cutoff_records, retention,
errors.
```
