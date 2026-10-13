# MODEL-EVIDENCE-01: which model actually ran each lane

A model's own "line 1" report is output, not evidence. This table takes each model id from metadata the runtime wrote. For Claude agents that is the `model` field the Anthropic API returned on every assistant message, in the agent's transcript. For Codex runs it is the `model` the Codex CLI recorded in the rollout's session and turn records. For Kimi it is the model the Kimi client recorded in `wire.jsonl`. Extracted 2026-10-13 by a read-only script over the local transcripts; the transcripts stay local.

| Run | Lane | Runtime-recorded model | Source | Matches the run record |
|---|---|---|---|---|
| R01 | advisor-fable | `claude-fable-5-1` (19 messages) | API metadata | yes |
| R03 | advisor-astra | `gpt-6-astra` | Codex rollout | yes |
| R04, R06, R14 | kimi-board | `kimi-code/k3-256k` | Kimi wire.jsonl (two sessions on disk) | was UNCONFIRMED; now confirmed for the recorded sessions |
| R05 | m4-prep | `gpt-6-sol` | Codex rollout | yes |
| R07, R08 | sol-query-check, publisher | `gpt-6.1-sol` requested; the server answered HTTP 400 | Codex rollout | yes (no model ran) |
| R09 | sol-query-check | `gpt-6-sol` | Codex rollout | yes |
| R10 | publisher | `gpt-6-sol` | Codex rollout | yes (its line 1 said only "GPT-6") |
| R11 | codex-probe | `gpt-6.1-sol` | Codex rollout | yes |
| R13, R15 | render-check (one agent, resumed) | `claude-sonnet-5-5` (10 messages) | API metadata | yes |
| R16 | leak-sweep | `claude-haiku-5-5` (47 messages) | API metadata | yes |
| R17 | redaction-fix | `claude-sonnet-5-5` (12 messages) | API metadata | yes |
| R18 | pub-gate | `claude-sonnet-5-5` | API metadata | yes |
| R19 | pub-review | `claude-sonnet-5-5` (54 messages) | API metadata | yes |
| L0 | controller | `claude-opus-5-5[1m]` (session configuration) | Claude Code session | n/a |

Limits: the Codex value is the model the client asked for and the server accepted; a 400 means no model ran. The Kimi client logs two names for the same model (`k3-256k` and `kimi-code/k3-256k`). From here on, `logs/runs.jsonl` cites this kind of metadata, and a line-1 self-report is a convenience only.
