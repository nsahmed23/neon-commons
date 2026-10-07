# Visual Workbench continuation

The visual workspace presents the existing `workbench` engine. It introduces no UI package, shell bridge, provider adapter or approval authority. The reference text terminal stays available. The operating profile for this implementation is an ANSI-capable Linux POSIX terminal and the existing CPython 3.12 runtime. Windows, Git Bash/mintty, macOS and native terminal accessibility remain qualification gates, not inferred support.

The application entrypoint is:

```sh
/workspace/intune-runtime/bin/python -B scripts/intune-iac.py workbench workspace --root /absolute/private/store --service-root /absolute/private/lab-service
```

The optional service root selects the existing explicitly synthetic maintenance route. Omit it when investigating observations without a modeled service. It does not select a production tenant or authorize writes. `--theme dark` uses charcoal/navy surfaces and cyan labels; `--theme light` uses a warm light surface. `--no-color` or `NO_COLOR` retains every label and status. `--reduced-motion` is accepted; both modes are event-driven and contain no decorative animation, unmeasured ETA, fake percentage or inferred rollout action.

When either stream is redirected, the host is not POSIX, or `TERM=dumb`, the workspace uses the entire reference line interface. The command syntax remains that displayed by `workbench terminal` and its `help`; JSON values stay escaped. The fallback is not native Windows qualification.

## Navigation and investigation

| Input | Effect |
|---|---|
| Up / Down, then Enter in Estate | Select the highlighted immutable object ID |
| 1 | Estate and the current bounded inventory page |
| 2 | Selected-policy inspector |
| 3 | Typed relationships with exact evidence and uncertainty |
| 4 | Persisted observation history |
| 5 | Revalidate the active exact plan; otherwise list operations and press Enter to review one |
| 6 | Explicitly labeled last execution/readback result, or persisted operation list; `:operations` refreshes and `:reconcile OPERATION_DIR` requests readback |
| 7 | Repository/observed/proposed/coverage view from the shared engine |
| 8 or ? | Complete text-command help |
| Tab | Next surface |
| n / p | Next / previous bounded engine page |
| h / l | Health / repository lineage |
| Page Up / Page Down | Scroll the exact result, including long values |
| : | Command bar accepting the existing text commands |
| / | Search policies/settings; preserve active global filters when using the four-view estate |
| f | Edit the shared engine’s global ownership/coverage/health filter command |
| b | Existing engine `back`: clear selected identity without dispatching mutation |
| q | Detach this interface; durable operations and independently scheduled collection remain separate |

Global filters use the same engine before pagination, not a filter on the currently visible page:

```text
views-page LIMIT OFFSET [QUERY [OWNERSHIP [COVERAGE [HEALTH]]]]
```

Use `-` for an unset field. For example, `:views-page 10 0 Privacy unknown complete_fresh -` searches the admitted inventory before selecting a page, shows matching versus inventory totals, and retains its filters for `n`, `p`, `/` and resume. Press `f` to edit these fields. Ownership admits `owned_here`, `owned_elsewhere`, `conflicting_claims`, `no_ownership_found_in_declared_scope` and `unknown`; coverage admits `complete_fresh`, `stale_or_incomplete` and `unknown`; health admits `fresh_failure`, `fresh_success`, `reporting_incomplete` and `unknown`. These are exact engine classifications, not new UI inference. A stale/incomplete ownership index remains unknown. Health does not dispatch a write.

Every presentation surface includes readable semantic labels above its complete typed evidence: immutable policy identity and targeting counts, typed relationship rows, snapshot/time history, exact-plan bindings, execution/recovery outcomes and distinct comparison baselines. Long results expose the current line range and total, with scrolling; the selected estate row has a literal `>` marker, not only color. Unknown, denied and incomplete results remain engine values. Color never carries the sole meaning. Narrow layouts keep the same commands; resize redraws without running another engine action.

Use the command bar for the existing intentional-change flow: `propose DESIRED_JSON NEW_OPERATION_DIR`, `review OPERATION_DIR`, explicit `execute OPERATION_DIR EXACT_REVIEW_DIGEST`, and `reconcile OPERATION_DIR`. The actual engine validates every command and retains its original authority and scope. A visible plan does not confer approval. This module neither derives nor inserts a digest, and it never creates a replacement plan. Production dispatch remains the separately configured protected worker contract; the synthetic route must not be presented as live execution.

While the synchronous engine is running, the frame says the outcome is not yet known. Returned typed results show actual completed/failed/unknown checks and journals. This UI does not invent sub-step progress during a blocking engine call. Persistent worker status remains inspectable through the command routes provided by that worker. Closing this terminal must not be advertised as cancellation of an external worker; no pause/resume button is exposed without engine support.

## Editing, recovery and context

The command bar supports Left/Right, Home/End, Backspace/Delete and Ctrl-U. Escape discards an unsubmitted edit; it does not cancel any operation. Bracketed multiline paste stays unsubmitted and becomes one bounded command; Enter must be deliberate. Input is bounded to 16,384 characters. Oversized edits are rejected in full. In redirected mode, the rest of an oversized physical line is drained without dispatching its suffix; draining stops after 64 KiB and closes input if no line boundary appears. The UI never writes arbitrary terminal-input escape sequences back to the screen.

`workspace-context.json` is a private, tenant-bound navigation record beside the existing store. It contains only selected immutable identity, a read-only view, an estate page/query and the current tab. It does not retain arbitrary command history, approval material, tokens, plan bytes or operation paths. Reopening validates the record and replays only a strict read-only allowlist through the engine. The current observations and history come from the store, not the navigation file. Invalid or cross-tenant context is rejected and preserved for investigation. A same-user navigation file is not an audit authority or hostile-host boundary.

Terminal attributes, cursor, alternate screen and bracketed-paste mode are restored on ordinary quit, EOF, SIGINT and exceptions. A cleanup failure is reported separately; an existing primary exception retains precedence and receives a safe cleanup note. Forced SIGKILL, terminal emulator failure and host power loss cannot execute cleanup code and are not covered by this guarantee. Interrupting an in-process operation retains the existing engine’s recovery semantics; inspect and reconcile an uncertain operation before retrying.

## Inert presentation and exact values

Imported controls, carriage returns, bidi/format characters and combining characters are rendered as visible escapes. Raw stored bytes are unchanged. Wide Unicode code points use East Asian W/F width two; other displayed characters use one. Combining and format sequences are escaped rather than allowed to conceal identity or status. Emoji grapheme composition is intentionally not interpreted. Exact JSON preserves list order, types, null and unknown keys; this renderer performs no policy normalization.

The renderer limits one displayed result to 200,000 wrapped lines and displays an explicit limit message rather than claiming completeness. Use the paged reference commands for a result above this limit. This is a presentation bound, not permission to remove evidence or expand the store’s admitted fleet envelope.

## Verification

Run the changed-scope regression through the actual workspace CLI:

```sh
/workspace/intune-runtime/bin/python -B -m unittest plugin_tests.test_workbench_tui_r4 -v
```

The tests exercise real Linux PTY keystrokes, resizing, hostile inert labels, edited/cancelled commands, bracketed paste, context reopen, EOF, SIGINT and terminal attributes. Their independent assertions inspect the persisted store and modeled service rather than relying on screen text for mutation safety. They are developer regression evidence; the separate independent evaluator drives the complete investigation/change/recovery journey and records its own expected values and terminal captures.

Performance thresholds were recorded before launch under `work/evidence/epoch-20261007-r4/visual/PREREGISTRATION.json`. The existing generator’s eight-policy limit required an explicit pre-measurement amendment, retained with the failed setup logs. Cold first-frame latency is bounded at five seconds and an input response at three seconds for this exact fixture. These observations cannot establish P99, fleet performance, Graph behavior or another host’s latency. Earlier 0.8.0 qualification remains historical and is not reused to qualify this new UI.
