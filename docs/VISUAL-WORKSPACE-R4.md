# Visual Workbench continuation

The visual workspace presents the existing `workbench` engine. It introduces no UI package, shell bridge, provider adapter or approval authority. The reference text terminal stays available. The operating profile for this implementation is an ANSI-capable Linux POSIX terminal and the existing CPython 3.12 runtime. Windows, Git Bash/mintty, macOS and native terminal accessibility remain qualification gates, not inferred support.

The application entrypoint is:

```sh
/workspace/intune-runtime/bin/python -B scripts/intune-iac.py workbench workspace --root /absolute/private/store --service-root /absolute/private/lab-service
```

The optional service root selects the existing explicitly synthetic maintenance route. Omit it when investigating observations without a modeled service. It does not select a production tenant or authorize writes. `--no-color` or `NO_COLOR` retains every label and status; section headings and recorded signal lines (`! ...`) stay bold, so structure never depends on colour. `--reduced-motion` is accepted; both modes are event-driven and contain no decorative animation, unmeasured ETA, fake percentage or inferred rollout action.

**Visual language.** The frame follows a technical drawing: fine, consistent rules, aligned labels and explicit connectors.
- **Rules.** On a UTF-8 terminal (and not the Linux console or `TERM=dumb`), the frame uses light box-drawing rules (`┌─┐ │ └─┘`). `--ascii` keeps `+-+ |` everywhere.
- **Themes.** Four themes share one information architecture: `dark` (charcoal surface, cyan labels; the default), `light` (a warm light surface), `blueprint` (a navy technical-drawing surface with light-blue text and white labels) and `high-contrast` (black surface, white text, yellow labels).
- **Words first.** Every state is written in words. Colour only reinforces fixed phrases and markers:
  - green: `[x]`, `NO CONFIGURATION CHANGE`, `REPOSITORY MATCHES THE RECORDED INTENT`, `succeeded_verified`, `desired_state_observed`, `matches desired`;
  - amber: `[?]`, `REPOSITORY CHANGED SINCE THE RECORDED INTENT`, `CHANGE COMPARISON UNKNOWN`, `outcome unknown`, `stale`;
  - red: `[!]`, `REFUSED`, `ERROR:`, `INPUT REJECTED:`, `REPOSITORY UNAVAILABLE`, `expired`, `not available`, `failed`.

  A bare word such as "verified" is never tinted, because it also appears in "NOT verified". A surface heading such as `[CHANGE REVIEW]` is bold. With colour off, the text is identical.
- **Focus and selection.** In Estate, `>` marks the row with keyboard focus and `*` the pinned selection that every other surface shows. They stay distinguishable when they differ.

When either stream is redirected, the host is not POSIX, or `TERM=dumb`, the workspace uses the entire reference line interface. The command syntax remains that displayed by `workbench terminal` and its `help`; JSON values stay escaped. The fallback is not native Windows qualification.

## Navigation and investigation

| Input | Effect |
|---|---|
| Up / Down, then Enter in Estate | Select the highlighted immutable object ID |
| o | Relationship overview of the estate: shared groups, filters, scope tags and settings first, then each policy; Up / Down and Enter select a policy, and `o` returns to the same place |
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
| i | Investigate: diagnostics for the selected policy on the Coverage surface |
| v | Delivery stages of the active operation on the Execution surface (`:delivery OPERATION_DIR` for any operation) |
| s | Start survey on the Help surface: what exists beside the store (sessions, repositories, exports, generated projects, services, operations), each with its states, and the next steps (`:start DIRECTORY` for another directory; see `WIZARD.md`) |
| Page Up / Page Down | Scroll the exact result, including long values |
| : | Command bar accepting the existing text commands |
| / | Search policies/settings; preserve active global filters when using the four-view estate |
| f | Lists every ownership, coverage and health filter, with the one in use marked `*`; Up and Down choose, Enter applies it as a read-only `views-page` query that keeps the other filters and the search, Esc closes. The typed form is `:views-page` |
| e / r / Esc | Typed details of the result shown / its complete raw record / back to the summary |
| a | Actions for the selected policy: each with its exact command (arguments taken from the recorded evidence, never parsed from prose), what it does, and whether it is available now with the engine's own reason when it is not. Enter puts the chosen command in the command bar for review; Enter there submits it, Esc discards it. A staged action is bound to its policy and tenant and is discarded, unsent, if the selection changes |
| b or :back | Back to the previous read-only view of this session; it never re-sends a command that prepares, approves, executes or records |
| :cancel | Nothing is running between commands, so it cancels nothing and says so: Esc discards a command being typed, Ctrl-C stops a running call and ends the session |
| ? | Help: the one reference for keys and commands |
| :clear-selection | Clear the selected policy. In the text interface the words `back` and `cancel` do the same; in the workspace they do what the two rows above say |
| q | Exit the workbench; the next start reopens the last read-only view. Durable operations and independently scheduled collection are not touched |
| Ctrl-C | Stops a running engine call and ends the workspace (status `interrupted`, exit 2). The result printed after the terminal is restored says what to check: diagnostics names anything the interrupt left unfinished; other processes, such as a scheduled collector, are not stopped. The next start reopens the last read-only view |

Global filters use the same engine before pagination, not a filter on the currently visible page:

```text
views-page LIMIT OFFSET [QUERY [OWNERSHIP [COVERAGE [HEALTH]]]]
```

Use `-` for an unset field. For example, `:views-page 10 0 Privacy unknown complete_fresh -` searches the admitted inventory before selecting a page, shows matching versus inventory totals, and retains its filters for `n`, `p`, `/` and resume. Press `f` to edit these fields. Ownership admits `owned_here`, `owned_elsewhere`, `conflicting_claims`, `no_ownership_found_in_declared_scope` and `unknown`; coverage admits `complete_fresh`, `stale_or_incomplete` and `unknown`; health admits `fresh_failure`, `fresh_success`, `reporting_incomplete` and `unknown`. These are exact engine classifications, not new UI inference. A stale/incomplete ownership index remains unknown. Health does not dispatch a write.

Every view opens as a readable summary; its complete evidence is one key away (`e` typed details, `r` raw record), never dumped below it. The summaries cover immutable policy identity and targeting counts, typed relationship rows, snapshot/time history, exact-plan bindings, execution/recovery outcomes and distinct comparison baselines. Long results expose the current line range and total, with scrolling; the focused estate row has a literal `>` marker and the pinned selection a `*`, not only colour. Unknown, denied and incomplete results remain engine values. Color never carries the sole meaning. Narrow layouts keep the same commands; resize redraws without running another engine action.

Use the command bar for the existing intentional-change flow: `propose DESIRED_JSON NEW_OPERATION_DIR`, `review OPERATION_DIR`, explicit `execute OPERATION_DIR EXACT_REVIEW_DIGEST`, and `reconcile OPERATION_DIR`. The actual engine validates every command and retains its original authority and scope. A visible plan does not confer approval. This module neither derives nor inserts a digest, and it never creates a replacement plan. Production dispatch remains the separately configured protected worker contract; the synthetic route must not be presented as live execution.

While the synchronous engine is running, the frame says the outcome is not yet known. Returned typed results show actual completed/failed/unknown checks and journals. This UI does not invent sub-step progress during a blocking engine call. Persistent worker status remains inspectable through the command routes provided by that worker. Closing this terminal must not be advertised as cancellation of an external worker; no pause/resume button is exposed without engine support.

## Context, changes and the repository

**Header lines.**
- The tab line numbers every surface and brackets the active one. When the full names do not fit, it uses short names (`[5 Plan]`, `9 Repo`). Narrower still, it never becomes bare digits: it names the active surface and says how to reach the rest (`[2 Inspector]  keys 1-9 switch surfaces; ? lists them`).
- **Hazard band.** When something recorded for the selected policy needs attention, a bold line under the context strip names the primary condition and the key for its response, on every surface, in every evidence layer, at every scroll position and size: for example `! Operation 651a8ce8: outcome unknown. Next: Reconcile it (a: actions); it never replays the change`. The response is named as the actions list names it, and the key is described as what it does: `a` opens the actions; it never performs the named action itself. The shortest wording, used at 40 columns, is `! Outcome unknown. Reconcile (a actions)`, the key line's own notation. The ranking is a service configured for another tenant than the store; then an operation whose outcome is unknown, diverged, whose records disagree or cannot be read; then a failed or unfinished collection; then a changed or unreadable repository; then a stale observation; then the proposal's own observation checks that diagnostics does not record (the modeled service or this policy changed since the observation, or it came from another service), each answered by collecting again. Every other finding is counted (`+2 more: 2`: the Inspector lists every one, the proposal's own observation check included), the same kind for another operation included; when the count does not fit beside the condition it takes a second row rather than being cut. The key line below always names the band's key (`a actions`, `i details`). The longest wording that fits is used, and every condition has one that fits whole at the minimum width. A recorded condition leaves the band only when a newer read no longer finds it: the workspace reads again after any command that may have written, and a status in a result (a journal status, for example) never hides one. A condition known only from this session's own result still shows until a read records it. If the read after a command fails, the conditions stay, marked `not re-read after collect: 2 re-reads`; with nothing recorded the band says `! Conditions not re-read after collect. 2: re-read`. Without colour the band is still bold, and its words carry the meaning on their own.
- When the proposal's own observation check failed, the strip's observation word says so (`OBSERVED service changed`, `policy changed`, `other source`, `other tenant`) instead of `fresh`, which only measures age; the Inspector lists the check under NEEDS ATTENTION with its response.
- The footer names the result's evidence class when it fits, otherwise its mode word (`[SYNTHETIC]`), otherwise nothing (the strip leads with the mode); it never cuts the class mid-word, and the approval statement takes its short form (`no auto-approval`) only when the full one does not fit.
- **Minimum size.** The documented minimum window is 40 columns by 12 rows: every band wording, its response and the whole short identities fit. Below it the workspace shows a constrained state instead of the surfaces: the evidence mode with the constraint (`SYNTHETIC; window below 40x12`), the tenant and policy with their hazard states, the primary hazard wrapped with its response kept whole (the count of other findings names no key, since no surface can be shown), the prompt and only the keys that work there: `q exits`, or `Enter submits; Esc discards` while a command is typed. When rows run out they are kept in this order: the hazard, the mode line, the prompt, the identities, the keys. Keys keep their meaning, and the full frame returns when the window is large enough.
- When the strip is too long, routine states (a fresh observation, a current repository) give way before hazards.
- The context strip below it leads with the evidence mode and the tenant. The mode is one word per evidence class, never the nearest-sounding one: `SYNTHETIC` (a modeled service), `CAPTURE` (an unverified export), `LABORATORY` (recorded responses; the source is not authenticated), `LIVE READ-ONLY` (an authenticated read), `MIXED` (more than one of these), `READ FAILED` (a read returned no policy) and `MODE UNKNOWN` (nothing observed yet, or a class this version does not name). An empty estate does not set a mode. Then the selected policy (name and short ID), the observation freshness, the repository state (from the Inspector's own checks when it has run) and the operation's status: the active operation's, or a recorded condition such as an unknown outcome that the Inspector's checks found, so it survives a restart.
- When the strip does not fit, it uses short labels (`OBS`, `REPO`, `OP`), then the policy's short ID, then short state words, then drops the operation and repository states. The mode and the tenant are never dropped.
- These are the facts the engine last reported for the selected policy. "unknown" or "not checked" means no result has said yet; the workspace never makes a hidden engine call to fill them in. Exact identities appear on each surface. The strip's state words are tinted like the body's, and a lineage result never stands in for the observation's freshness.
- The title names the surface and, when a key opens a view that belongs to it, that view too: `Coverage / Diagnostics`, `Coverage / Health`, `Execution / Delivery`, `Help / Families`, `Repository / Repository entry`.

**Frame lines.**
- When the body continues above or below what fits, the border says so (`more above: PgUp`, `more below: PgDn`).
- The status line gives the evidence class of the result, or of the selected policy's observation when a view has none. It shortens only that class to fit, so `rows` and `no automatic approval` always stay whole.
- The notice starts with `Ready.` when the workbench waits for input. It then says what was shown: for the read-only views, the view's name and that viewing changed nothing (scoped to that action: the screen may show an operation that ran earlier). It does not repeat the keys (the key line lists them) or the policy (the context strip names it). After any other command (propose, execute, reconcile, collect, an import or a refresh) it says the command ran and the status the engine reported, never that nothing happened. A refusal notice says `REFUSED` and that the meaning and next step are on the screen only when the workbench explains that code; the code itself is the first line of the body. It is shortened at a word with an ellipsis.
- The key line shows the longest of three forms that fits, so every width keeps `? help`, `: command`, `b back` and `q exit`. Inside typed details it reads `e summary`, inside the raw record `r summary`, because the same key returns there.
- Evidence layers: each view ends with one line, `Evidence: e typed details | r complete raw record (N lines)`. `e` shows every field of the result as a readable outline (names spaced for reading, absent values and yes/no in words, lists numbered); a name longer than its label column keeps every character on its own line, with the value beneath. `r` shows the complete raw engine record exactly as returned. Esc, or the same key again, returns to the summary. The title names the layer (`Inspector / typed details`). A record longer than the view limit says where it continues complete (the text interface).
- From 150 body columns, typed details or the raw record open beside the summary instead of replacing it.
- With box-drawing rules, Relationships draws connected tree lines and Delivery hangs its stages from one spine. ASCII rules keep the plain list.
- Colour pairs meet WCAG AA (4.5:1) in every theme; a test measures each role against its background.

**Inspector (2).** Answers three questions from the engine's read model. The order is name, identity and provenance, then what needs attention, then what can be done next, then the evidence in detail, so a long settings list never pushes the first answers below the fold:
- **What it is and what the evidence says it does:** name and exact identity, platform, technologies and scope tags. Then one line of provenance: the evidence mode, run and time; what that run covered (`complete` reads "policy list, settings and assignments read in full"; anything else names the collection state and points to `i`); and freshness. Then each setting's definition and exact value, and each target (include, exclude, all devices or all licensed users) with its group and filter. A choice value's meaning is never translated: the line says it is not established, and `d` shows what is known. Group names are shown only where they were captured; otherwise the line says they were not, and the identities stay. Then the description, ownership, and where a repository intent was recorded.
- **What needs attention:** the signals diagnostics records for this policy, each as its recorded fact (for example the observation's own freshness, or a repository that changed; the two are never merged into one cause). When none is recorded, it says so and names the areas that were checked. Areas that were not examined (no repository intent recorded, device evidence not imported, partly read, unreadable) are named on one line, `Not fully checked`, never counted as checked. When diagnostics could not be read, it says that instead.
- **What can be done next:** the recorded next steps first, otherwise the change route that exists (repository intent recorded: `propose-from-intent`; none: `repository-entry` or `propose`). Each names a real command. A change step says it prepares a proposal and its review digest, that `review` shows it, and that nothing is approved until `execute` is given that digest. When diagnostics could not be read, or were read only in part, no change is offered: the first step is `i`, because whether anything needs attention is not established. At most three steps are shown; the line after them counts the rest, which `i` lists.

The literal-capture fields are in the typed details and the raw record. `d` opens the dictionary for these settings on the same surface (`[SETTING DICTIONARY]`). It keeps four sources separate:
- **Vendor documentation:** name, meaning, aliases, CSP path, type and default, the documented CSP values, applicability, publisher, dates and URL.
- **Local mapping:** support status, permitted Graph values and deferred qualifications.
- **Observed use:** each policy using the setting, with its value, freshness, coverage and evidence class.
- **Company, community and AI categories:** each with its availability.

When the vendor record says the Graph-to-CSP value translation is unverified, the dictionary says so next to the CSP values instead of pairing them.

**Relationships (3).** Typed edges are grouped as targeting, configuration, source and lineage, and ownership, drawn as a dependency list. Each edge shows its exact target; an assignment also shows its filter. The evidence class is stated once on a group's heading when every edge in the group shares it, and on each edge otherwise. The selected repository source appears as a lineage edge, and the writer ownership shows its status and reason.

**Lineage (`l`, on Relationships).** `[REPOSITORY LINEAGE]` follows each effective value of the selected policy's component through Atmos inheritance to the repository file, line and column that defines it, and lists the earlier definitions it overrides (for example `/command` defined in the stack file over `atmos.yaml`). Long policy keys are written once as `<key> = p_…` and abbreviated as `<key>` below. Values are never shown here; they stay in the Inspector and the change review.

The source is one of three, in this order: a resolution captured with the observation, one recorded by an adoption, or else the policy's latest repository intent from `repository-import` or `repository-refresh`. The source is named with its revision and whether its content was verified. Lineage from an intent is "recorded intent not revalidated"; the Repository surface (9) says whether the repository still matches it. The context strip keeps the observation's freshness, not lineage's. A cleared selection (`b`) says so and how to select again.

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

**Relationship overview (`o`, on Estate).** `[ESTATE OVERVIEW]` answers what the estate's policies have in common. It is built from the records Estate and Relationships already use: each policy's current observation and typed edges, its ownership and freshness, and the maintenance queue's findings.
- The first line counts policies read against the store's total and those without a complete observation, and lists ownership.
- Then, most-shared first, as connected trees: targeted groups (included and excluded by which policies), filters, scope tags, and settings configured by more than one policy, with the number of distinct settings.
- Then each policy: groups, exclusions, filters, settings, owner, freshness and its findings.
- Last, NOT ESTABLISHED: policies without a complete observation, and any beyond the read bound (200 by default). It says plainly when nothing was left out.

Up and Down move the focus marker `>` over the policies, and Enter selects one. Selecting carries the policy into every surface, and `o` returns to the overview at the same policy. `workbench estate-overview --root STORE [--limit N]` prints the same value as JSON.

**Families (`:families`, on Help).** `[POLICY FAMILIES]` lists every policy, application and script family from the product's `family-coverage.csv`, unchanged: its stage, route and material, the qualification it still needs, and its live status. One column is added: where the family appears in the workbench today. Settings Catalog policies are in the estate and every maintenance route. Groups, filters and scope tags appear as referenced targets, never managed. Every other family is "not in the estate". Estate's header says that it lists Settings Catalog policies only. `workbench families` prints the same table as JSON.

**Diagnostics (`i`, on Coverage).** `[DIAGNOSTICS]` shows what needs attention for the selected policy. It also lists every area it checked, so silence never means "not looked at". Each signal gives the observed fact, its evidence (run, operation, intent, source file) and the next step:
- **collection:** this policy's last collection failed (its retained last-good observation is named, now stale, or the view says none exists yet), or a run started and recorded no end.
- **freshness:** the newest observation is stale for another reason, named from the store: older than the freshness window (its length in seconds is given), or stamped later than this host's clock read when it was checked (an observation from a collector whose clock runs ahead stays stale until the clocks agree, and the step says so); or the policy has never been observed completely. The inspection itself carries `freshness_reasons`, `freshness_window_seconds` and `freshness_checked_at`.
- **operations:** an outcome is unknown, so reconcile it (never replayed). That includes a dispatch that stopped before its result was registered: the journal is read for every prepared operation, so the store's "prepared" cannot hide it. Also a journal that disagrees with the store record, or a reconciled operation that diverged from both the plan and its starting point. Operations are read in bounded pages, newest first; past the bound the area says "partly checked".
- **repository:** the repository changed since its recorded intent (changed, added and removed files), it cannot be resolved, its component no longer consumes exactly this policy (proposals refuse it), or intents come from two repository scopes (which no further import resolves in this store).
- **device evidence:** a truncated capture or access errors, so missing devices are unknown, not failed; or cohort membership conflicts.

An area that cannot be read is listed as "could not be read" with its error, and the other areas still show. With no signal, the summary says "nothing needs attention in this store's records", or that some areas were not fully read.

It reads local records only, and the same view is `workbench diagnostics --root STORE --object OBJECT_ID`.

**Plan (5).** A review starts with `[CHANGE REVIEW]`:
- each changed field with its exact observed and desired values. Strings are quoted, and `null`, `""` and an absent value stay distinct.
- Side by side when the terminal is at least 96 columns wide and the values fit; otherwise, before and after on stacked lines.
- Setting changes name the setting record, its definition and the changed path. Assignment changes list targets added and removed.
- An order-only change to the settings list is named, because the plan treats it as a change.
- An unchanged proposal says `NO CONFIGURATION CHANGE`. This label comes from the plan itself.
- The plan's change tags and the cited repository intent's freshness follow, then the `[PLAN REVIEW]` fields, with expiry shown as a UTC time.

**Coverage (7).** Adds the repository intent's freshness and a `[REPOSITORY VERSUS OBSERVED]` table in the same form.

**Delivery (`v`, on Execution).** `[DELIVERY]` lists the active operation's eight stages in order, each with a marker and its state in words:
1. **Proposal:** when it was recorded and the repository intent it cites, with that intent's freshness. If the context
   file the plan bound has changed since, it says so and that the citation is unknown; it never reads one from the
   changed file.
2. **Review:** the changed fields (or `NO CONFIGURATION CHANGE`) and the plan digest.
3. **Approval:** waiting until the plan's approval window closes, expired, not yet open (the local clock reads earlier than the plan's preparation), or done with the exact review digest supplied at dispatch.
4. **Execution:** the engine and service results, or `outcome unknown` with its recorded error.
5. **Readback:** the independent readback's classification, second plan, visibility and mismatches.
6. **Reconciliation:** not needed, required, or its result.
7. **Deployment record:** recorded, available, not available (for example after a lost response, because the execution's own readback was never verified), or not applicable when no repository intent was cited.
8. **Observed after:** whether the newest observation from the same service, at a service revision later than the plan's, matches the desired configuration. The comparison uses the collector's service revision, not clock times, and a difference is shown field by field.

Below the stages, `HISTORY` lists every event of the operation's journal in its recorded order (the hash chain is verified when the operation is loaded): prepared, dispatch started, the engine's result, the service's answer or that nothing was sent, verified, outcome unknown with its error, reconciled with its classification. Each says what it recorded. The journal itself records no times. A time appears beside an event only where the store registered the journal right after it: the store keeps the journal's digest with each registration, and the pairing holds only when the journal cut after that event, with the registered status, has exactly that digest. Every other event reads `time not recorded`; a registration that pairs with no event is counted, not attached. The prepared event names the digest approval will need; the dispatch event names the digest it was approved with. In the record, `mutation_dispatched` is true only with a recorded service answer, false only when nothing was sent (no configuration change), and null otherwise: after a lost response or an interrupt, whether the change reached the service is not established.

Then `CI WORKFLOW RUNS (imported claims; not verified)` lists the CI runs recorded with `workflow-import` that name this operation, and those that name no operation but the repository revision its intent cites (a run that names another operation belongs to that one): workflow, run, claimed status, revision, observation time and link. They stay apart from the stages: an imported `success` never marks a stage done. With none, one line says so and names `workflow-import`. On any surface, a record the store has just accepted (`workflow-import`, `device-evidence-import`, `repository-import` and the others) opens with `[RECORDED]`: its kind, short identity, whether it is new or was already recorded (nothing changed), and for a CI run what it claims and which local operation or observation it links to.

The markers are `[x]` done, `[ ]` waiting or not yet, `[-]` not needed, `[?]` unknown or required and `[!]` stopped: failure, expiry or refusal (the legend avoids the alert words, so only its markers are tinted). A `Next:` line names the one step that would move the change forward. It never inserts the review digest into a command. The view only reads the operation's records and the store, and it is not saved for reopening: the navigation record never holds operation paths.

**Repository (9).** Runs the read-only `repository-status` for the selected policy:
- whether the repository still matches the recorded intent;
- the source, physical and logical stack, component, pointer and revision (content verified or asserted), and the consumer contract;
- for a stale intent, the changed, added and removed sources and the exact field changes between the recorded intent and the repository now;
- the next step.

**Commands.**
- `:repository-refresh REVISION` records the current source as a new intent.
- `:propose-from-intent NEW_OPERATION_DIR` prepares a proposal from it, with the digest its review needs.
- Neither approves anything; approval still needs the exact review digest with `:execute`. Reopening the workspace restores the Repository surface like any other read-only view.

**Entering an existing repository (`:repository-entry REPOSITORY`, on Repository).** `[REPOSITORY ENTRY]` surveys a repository without changing it and without asking anything first:
1. It discovers the repository under the same literal Atmos rules as `repository-import`. It reads the checked-out commit from `.git` and lists each stack and component with how many policies it holds.
2. It lists every entry of each component's `vars.policies` as a numbered policy. Each shows the observed name (from this store's observations only; no stack value is printed), the stack and component, its state in this store, the import key, the backend the component's files declare (`local` when none is declared), and the resource address when the generated reference component consumes exactly that policy.
3. Each state says what happens next:
   - ready to record;
   - recorded (current or stale, with the refresh step);
   - recorded from another repository (a second source would make status, refresh and proposals refuse the policy);
   - refused because the component does not consume exactly this policy;
   - needs the object ID, a commit, the backend or the resource address;
   - belongs to another tenant.

Up and Down move the focus marker `>` between policies. Enter on a policy puts its exact `repository-import` command in the command bar for review: nothing runs until the engineer submits it, and Esc discards it. A policy with nothing to run explains why instead. `workbench repository-entry --root STORE --repo REPOSITORY` prints the same survey with each command in shell form, and `start` points to it for every repository it finds.

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

## Distinct states

Under the policy's identity, the Inspector shows three states, each from its own records, where it used to show one provenance line:
- **Observation:** where the evidence comes from (mode, run, time to the second with its zone), what the run covered, and its freshness by age with the store's reason when it is not fresh. Beside it, not folded into it, the proposal's own check against the service when that fails: `fresh by age; the modeled service changed since (revision 1, now 2)`.
- **Intent:** the recorded repository intent (its id, stack and component, revision, whether that revision was verified against the files) and whether the repository still matches it, with the changed file when diagnostics recorded one; or `none recorded` with the command that finds where the policy is maintained.
- **Operation:** the policy's newest operation as its journal says (with the store's record when the two differ) and its readback when reconciled; or `none recorded for this policy`.

Summaries give times to the second with their zone (`2026-10-14 19:55:52 UTC`); the exact values stay in the typed details (`e`) and the raw record (`r`). The `Managed` line then states only ownership, since the intent has its own line. The Repository status and the Plan review open with the same three states, from the last read of the policy and labelled so; status words read as words (`outcome unknown`).

## Times

Every summary gives recorded times to the second with their zone (`2026-10-14 12:25:00 UTC`): diagnostics sentences, Delivery stages and the approval window, histories, operations, health, CI runs, recorded results, lineage, Relationships and the Plan review. The exact values stay in the typed details (`e`), the raw record (`r`) and each diagnostics signal's evidence.

## Help

Help (`?`, surface 8) opens with KEYS: one key per row, each bound in the workspace, in the order an engineer reaches for them. WORDS AND RULES follow: the mode words, the context strip, the `!` line and its count, the STATE block, how changes work, and what the next start reopens (the last read-only view of the selected policy; Delivery and repository-entry views, which hold paths, are not reopened).

## Group identities

No surface captures group names today. Every group target says so beside its identity, `Unresolved group identity 4444…`, in the Inspector, the change review and Relationships; the estate overview says it once for its list. A group is never given an invented name or read as all users; a name the evidence carries is shown with its identity.

## Guided actions

The Inspector's read model offers, for the selected policy, the actions that fit what is recorded:
- **Show what diagnostics could not read** (`diagnostics`) comes first whenever an area a change depends on (collection, freshness, operations, repository) was not read completely, including a bounded operations read that found something. Until it is read, whether anything needs attention is not established, so no change is offered: the proposal is shown as blocked by the workspace (`workbench_attention_not_established`). The engine itself would still accept the command typed by hand.
- **Reconcile** each operation whose outcome is unknown, diverged or whose records disagree, one action per operation in the band's order, with that operation's own directory from the recorded signal. It reads the modeled service, records a receipt and a journal entry and records the operation in this store; it never replays the write. For a diverged operation it is labelled as a read only: a divergence needs a reviewed change. Unreadable records offer no reconcile; the band points to the diagnostics.
- **Collect again** after a failed or unfinished collection or a stale observation, and whenever the proposal's own observation check names collecting again as the fix. It reads the modeled service and records a collection run, including a denied or partial one. Without `--service-root` it is offered as blocked, saying what it needs.
- **Refresh the repository intent** (`repository-refresh REVISION RESOLUTION_SHA256`) after the repository changed. Choosing it shows the source difference first (the Repository surface), and only then stages the command, bound to the resolution digest of the difference shown; if the repository changes again before submission, the engine refuses (`workbench_difference_changed`) and the difference has to be reviewed again. The revision is the one input still needed: with no pinned git here it is recorded as asserted, not verified against the files. It is not a Git commit, an approval or an apply.
- **Prepare a proposal** from the recorded intent (`propose-from-intent`), or from a desired file when no intent is recorded (`propose`, with the desired file as the input still needed). The operation directory is new and beside the store, named with a random part, and neither it nor its sibling input files exist. It is blocked with the engine's own code by the same checks submission makes, in the same order: the repository changed since its intent (with the cause diagnostics recorded), a desired value outside the supported capability map, a desired body the model does not accept, or an observation that cannot ground a proposal. That last check is the function `propose` runs under the service lock, read here without the lock and without writing, so submission still rechecks everything. Because one engine code covers several causes, the block also names which check failed, from the recorded facts: for example `maintenance_observation_stale: the modeled service changed after this observation was collected (revision 1, now 2); collect again`. The observation can be fresh by age and still fail this check, which is what happens after an execution changes the service. `propose-from-intent` writes its two input files before the observation is checked, so a refusal there leaves them beside the directory that was never created; the effects text says so.
- **Find where this policy is maintained** (`repository-entry REPOSITORY`) when no intent is recorded.
- **Record the deployment** (`deployment-record OPERATION_DIR INTENT_ID`) of the policy's newest operation, offered
  exactly when Delivery's own deployment-record stage says it is available: the operation was verified by its own
  readback, its plan cites a repository intent, its bound context file is unchanged, and nothing is recorded for it yet.
  The read model asks the same function Delivery uses (`workbench_delivery.deployment_stage`). The command rechecks
  everything (`record_local_deployment`), records a deployment receipt in the store as a verified local modeled
  baseline for that intent (not platform qualified) and sends nothing to the service. Once recorded it is no longer
  offered. The same command can be typed in the workspace; Delivery's next step names it first and the shell form
  (`workbench deployment-record --root STORE --operation OPERATION_DIR --intent INTENT_ID`) second. The native Windows
  workspace does not accept it yet.

Each action is bound to the tenant, the policy and the evidence mode it was read for (and an operation or a shown difference where it has one). A staged action whose policy, tenant or evidence mode changed before submission is discarded unsent.

In the Inspector each recorded condition is followed by its own `Next:` line, and an `ACTIONS` list says which are available and why the others are blocked. Execution is never offered here: it keeps its exact review digest, typed by the engineer from the plan review.

While the action list is open, its own key line applies (`? help | Up/Down choose | Enter stages | Esc closes | q exit`). Each action shows its name, whether it is available (or the engine's reason it is not) and one essential effect; the focused action also shows its exact command and its full effects.

While an action is staged, the two rows above the command bar give, first, its complete boundary (what it does and does not do) and then what to type and how to submit or cancel, each in the longest complete form that fits: for a refresh `STAGED refresh: records a new intent only; no Git commit, approval or apply.` (`Refresh: no commit, approval or apply.` at 40 columns) above `Type REVISION at the cursor; the digest after it pins the reviewed difference. Enter submits; Esc cancels.` The body gives up one row for it.

A refusal says what it established about what changed, from the engine's own facts, in an `Effect:` line between the cause and the next step: for a refresh refused because the repository changed after its difference was shown, `No new intent was recorded; the previous intent <id> is retained.`; for a proposal refused after its input files were written, the files that remain; for an execution refused before dispatch, `Nothing was dispatched.` An execution whose response was lost says that dispatch started and whether the service applied the change is unknown; reconcile checks it without repeating the change. A refusal whose effect the engine did not establish says nothing about effects.

`a` reads the actions again every time it is pressed, through the same `inspect` command the Inspector uses; the list opens over the current screen and Esc returns to it. After any command that is not a read-only view, the workspace also reads the selected policy again on its own, so the band and the actions follow what that command recorded while the screen keeps its result. If that read fails, the conditions stay on the band marked as not re-read, the notice says so, and the actions are dropped until `a` reads them again. The command bar submits with Enter, or Ctrl+Enter in the native Windows console; the staging notice and the action list name the key of the session.
