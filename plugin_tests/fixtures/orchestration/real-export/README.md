# Real orchestration export fixture

`header.json` and `events.jsonl` are an `orchestration-export/1` made by `loopctl export` (loop commit f96030d, which
exports the tree a completion recorded) from the evidence loop's custody copy of its event store
(`lanes/evidence-loop-01/loop-store/events.jsonl`, 158 events, taken 2026-10-15). The events were appended to a
temporary store and exported; nothing in them was edited. The export is an allowlist: no prompt, result, summary,
producer identity beyond the role, session id or agent configuration is in it.

A scan for absolute home paths (`/home/`, `Users`, the account name) found none. Evidence paths are
`C:/Dev/Projects/intune-rescue/...` and `C:/Dev/Projects/agent-telemetry/...`, which the tests configure as evidence
roots. The header's `exported_utc` is fixed at 2026-10-15T19:40:00Z so the fixture is reproducible.

The task `T-f445e27aa6` (events 27 to 44) is the case the view must get right: timed out, `unknown` (cleanup not
confirmed after cancel), then a controller-attested cancel, then a late result. It reads "unknown; later cancelled
(attested by the controller); late result recorded", never cancelled.
