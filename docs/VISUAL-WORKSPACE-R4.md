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
| 9 | Repository status of the selected policy: is its recorded repository intent still current, and what changed |
| Tab | Next surface |
| n / p | Next / previous bounded engine page |
| h / l | Health and reporting on the Coverage surface / repository lineage |
| d | Setting dictionary for the selected policy's settings |
| m | Maintenance queue on the Coverage surface |
| v | Delivery stages of the active operation on the Execution surface (`:delivery OPERATION_DIR` for any operation) |
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

## Context, changes and the repository

**Header lines.**
- The tab line numbers every surface and brackets the active one. When the full names do not fit, it uses short names (`[5 Plan]`, `9 Repo`).
- The context strip below it shows the tenant, the selected policy (name and short ID), the observation freshness, the repository state and the active operation's status.
- When the strip does not fit, it drops the tenant first, then uses short labels (`OBS`, `REPO`, `OP`), then the policy name.
- These are the facts the engine last reported for the selected policy. "unknown" or "not checked" means no result has said yet; the workspace never makes a hidden engine call to fill them in. Exact identities appear on each surface.

**Inspector (2).** Shows the selected policy as an engineer reads it:
- name and exact identity;
- platform and technologies;
- scope tags, quoted;
- observation time, coverage, freshness and snapshot;
- ownership;
- the description, quoted;
- a settings table: record ID, definition ID and the exact configured value by instance kind (choice, value or ordered list);
- a targeting table: include, exclude, all devices or all licensed users, each with its group and filter.

The literal-capture fields remain. `d` opens the dictionary for these settings on the same surface (`[SETTING DICTIONARY]`). It keeps four sources separate:
- **Vendor documentation:** name, meaning, aliases, CSP path, type and default, the documented CSP values, applicability, publisher, dates and URL.
- **Local mapping:** support status, permitted Graph values and deferred qualifications.
- **Observed use:** each policy using the setting, with its value, freshness, coverage and evidence class.
- **Company, community and AI categories:** each with its availability.

When the vendor record says the Graph-to-CSP value translation is unverified, the dictionary says so next to the CSP values instead of pairing them.

**Relationships (3).** Typed edges are grouped as targeting, configuration, source and lineage, and ownership, drawn as a dependency list. Each edge shows its exact target; an assignment also shows its filter. The evidence class is stated once on a group's heading when every edge in the group shares it, and on each edge otherwise. The selected repository source appears as a lineage edge, and the writer ownership shows its status and reason.

**History (4).** Observations newest first. Each shows its time, collection run, coverage and snapshot, then its evidence class, recorded change time and attribution (both `unknown` unless evidence records them). It then compares the observation with the one before it on the same page:
- `No configuration change since the previous observation.`;
- or the exact field changes, in the same form as the change review;
- or, when a field was not completely observed, an unknown comparison with its reasons. Incompletely observed fields are listed by name.

The last observation on a page says it is the earliest on that page, and whether `n` shows older ones. Observation time is when collection saw the configuration; the screen says it does not establish who changed it or when.

**Coverage (7), health and maintenance.** `h` shows `[HEALTH AND REPORTING]` for the selected policy:
- the imported device evidence: class, as-of time and cohort version;
- the denominator: targeted, eligible and excluded devices, membership conflicts and reports from devices outside the cohort;
- the source file and its digest;
- a stage table (object, assignment, cohort, receipt, execution, effective state, outcome) with targeted, reported, success, failure, pending, unknown-status and no-fresh-report counts.

The full table fits 80 columns; narrower terminals get abbreviated columns with a legend, then sentences. For the deepest stage with any fresh report, the screen states the result in words ("8 of 100 targeted devices reported success at execution; 92 without a fresh report"), why the rest are not counted, and a device matrix with one cell per device (or per stated group of devices above 400). Endpoint health and outcome, service acceptance and configuration parity, and rollout readiness and approval follow on separate lines. Without imported evidence it says so. The estate-wide health result adds the collection's freshness, last success, last attempt, retained last-good state and pending observations.

`m` shows `[MAINTENANCE QUEUE]`: each finding with its priority, affected object, the reason it matters, action state, owner assertion, freshness, review assignee role, writer ownership, source owner claim, review state, review due date, exception expiry, compatibility profile, evidence and related proposals (one line per operation with its latest journal status). The queue never remediates automatically. Both views resume after reopening.

**Plan (5).** A review starts with `[CHANGE REVIEW]`:
- each changed field with its exact observed and desired values. Strings are quoted, and `null`, `""` and an absent value stay distinct.
- Side by side when the terminal is at least 96 columns wide and the values fit; otherwise, before and after on stacked lines.
- Setting changes name the setting record, its definition and the changed path. Assignment changes list targets added and removed.
- An order-only change to the settings list is named, because the plan treats it as a change.
- An unchanged proposal says `NO CONFIGURATION CHANGE`. This label comes from the plan itself.
- The plan's change tags and the cited repository intent's freshness follow, then the existing `[EXACT PLAN REVIEW]` fields, with expiry shown as a UTC time.

**Coverage (7).** Adds the repository intent's freshness and a `[REPOSITORY VERSUS OBSERVED]` table in the same form.

**Delivery (`v`, on Execution).** `[DELIVERY]` lists the active operation's eight stages in order, each with a marker and its state in words:
1. **Proposal:** when it was recorded and the repository intent it cites, with that intent's freshness.
2. **Review:** the changed fields (or `NO CONFIGURATION CHANGE`) and the plan digest.
3. **Approval:** waiting until the plan's approval window closes, expired, not yet open (the local clock reads earlier than the plan's preparation), or done with the exact review digest supplied at dispatch.
4. **Execution:** the engine and service results, or `outcome unknown` with its recorded error.
5. **Readback:** the independent readback's classification, second plan, visibility and mismatches.
6. **Reconciliation:** not needed, required, or its result.
7. **Deployment record:** recorded, available, not available (for example after a lost response, because the execution's own readback was never verified), or not applicable when no repository intent was cited.
8. **Observed after:** whether the newest observation from the same service, at a service revision later than the plan's, matches the desired configuration. The comparison uses the collector's service revision, not clock times, and a difference is shown field by field.

The markers are `[x]` done, `[ ]` waiting or not yet, `[-]` not needed, `[?]` unknown or required and `[!]` failed, expired or refused. A `Next:` line names the one step that would move the change forward. It never inserts the review digest into a command. The view only reads the operation's records and the store, and it is not saved for reopening: the navigation record never holds operation paths.

**Repository (9).** Runs the read-only `repository-status` for the selected policy:
- whether the repository still matches the recorded intent;
- the source, physical and logical stack, component, pointer and revision (content verified or asserted), and the consumer contract;
- for a stale intent, the changed, added and removed sources and the exact field changes between the recorded intent and the repository now;
- the next step.

**Commands.**
- `:repository-refresh REVISION` records the current source as a new intent.
- `:propose-from-intent NEW_OPERATION_DIR` prepares a reviewed proposal from it.
- Neither approves anything; approval still needs the exact review digest with `:execute`. Reopening the workspace restores the Repository surface like any other read-only view.

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
