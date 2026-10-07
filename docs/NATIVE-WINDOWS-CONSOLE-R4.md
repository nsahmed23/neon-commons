# Inactive native console, input and navigation context seam

This extends the existing Workbench Workspace and complete command engine. It is not a second terminal product, an execution implementation, or activation of a native Windows host profile. The existing POSIX terminal and no-TTY text routes remain unchanged until a reviewed integration qualifies equivalent storage and native behavior.

The reviewed shared Workspace/command-engine seam is now integrated and was committed in checkpoint 9, `f58bbad`. Its actual-repository changed scope passed 45 tests; the earlier staged 16-test POSIX receipt remains historical overlapping evidence. The native adapter remains inactive and native Windows behavior remains unqualified. The integration adds no ordinary host-profile activation or native execution permission. Historical staging notes below describe the preserved pre-integration work.

## Native console capability

`windows_terminal.NativeConsole` acquires the actual input/output console handles through `GetStdHandle` and validates both with `GetConsoleMode`. It uses actual `SetConsoleMode`, `WaitForSingleObject`, `ReadConsoleInputW`, `GetConsoleScreenBufferInfo` and `WriteConsoleW`, with explicit ctypes layouts/prototypes. Native construction on another host fails before a Win32 call. A console mode failure identifies redirected input/mintty as unsupported for this visual adapter; it does not make the private store portable.

The session retains exact original input/output modes, enables only reviewed raw key/window input and VT output, checks the mode readback, and restores both modes and the existing ANSI alternate-screen/cursor state on normal return, EOF, cancellation or exception. Cleanup failure is explicit and must preserve an earlier primary error. Standard handles belong to the process and are not closed. No subprocess, network access, token, permission change or worker control occurs.

The key-reader emits existing Workspace navigation and text events. Resize events redraw. UTF-16 surrogate pairs decode strictly; unmatched surrogates and unknown control sequences cannot become commands. Repeated text/navigation are bounded; submission/interrupt is never repeated. Input callbacks use bounded waits so interruption remains observable.

`ReadConsoleInputW` does not prove whether an Enter came from clipboard paste. The inactive native profile therefore requires an explicit native command-submit gesture: Ctrl+Enter yields a distinct `submit` event; ordinary Enter navigates but does not submit an edited command. Workspace receives a `submission_key` capability parameter, defaults to its current POSIX Enter behavior, and uses `submit` only for this native adapter. Pasted newline/tab/control input must not auto-dispatch. Native Windows Terminal/conhost paste, IME, Unicode and keyboard-layout tests remain mandatory; a modeled event stream is not native evidence. Mintty does not inherit this claim and uses the complete text interface only after a separately supported private-store route is available.

## Existing Workspace/engine integration seam

The integrated bounded seam adds an exact private native binding to Workspace. Defaults preserve current behavior. Its inactive composition factory accepts only an exact WindowsWorkbenchStore, exact WindowsWorkspaceContext and exact NativeConsole. The root command engine gets the same exact admitted store through an internal store-capability parameter, not a user JSON flag, environment variable, changed host gate or arbitrary store factory. The factory calls the existing run_terminal/Workspace receive/input methods. No ordinary parser route selects it.

Native context persistence reuses the current exact Workspace navigation validator and tenant binding. It contains only readonly selection/page/history/service review/status/attach navigation, never pending edits, command queues, signatures or operation approval. It uses the existing pinned native private-directory capability and cooperative native file lock. New generations are exclusively published and chained by sequence/predecessor/hash; no mutable latest pointer or unchecked Path.write_text/chmod fallback exists. Conflicting, gapped, wrong-tenant, changed or saturated histories fail explicitly and remain available for inspection. Bounded size/count and no-op saves limit churn. Native durability limitations remain those of the reviewed filesystem adapter.

## Qualification sequence

1. Local non-Windows construction rejection and modeled ABI/key/session/context fault tests, each labeled laboratory only.
2. Preserve POSIX Workspace/no-TTY/text regressions after the narrow seam integration; no full historical suite repetition.
3. On an authorized Windows host: actual handles/modes before, during and after; navigation/inspection; exact context close/reopen; Ctrl+Enter intentional submission; multi-line clipboard paste produces zero command dispatch until explicit submit; Unicode/IME/resize; EOF/interrupt and primary-plus-cleanup failure; redirected handles and mintty fail visual admission.
4. Use the same existing engine with the independently qualified native store/reader; collect real PowerShell/Git Bash/Windows Terminal and conhost evidence. No live Graph/backend/device/CI gate is replaced by these console results.

Source was staged outside `intune_iac` for review before checkpoint 9 integration. Native Windows behavior is unqualified on the current Linux host, and organizational production approval is absent.

## Staged implementation and bounded evidence

`windows_terminal.py` and `windows_workspace_context.py` implement the inactive native primitives. The terminal stage has 11 local ABI/key/session checks (including actual non-Windows constructor rejection); context has 10 local file/lock/publication model checks using the real existing navigation validator. These scopes do not qualify a Win32 call, NTFS durability, clipboard or IME behavior. `QUALIFICATION.json` pins exact sources and logs.

The context history cap is 256 immutable generations, with a 128 KiB per-generation bound verified before and after native handle reads. Identical navigation is a no-op. Saturation fails and retains the entire history; automatic deletion/compaction is not implemented. Native Alt/AltGr key combinations are presently rejected; international layout/IME support remains explicit implementation/qualification work before a broader native console profile is admitted.

`scripts/qualify-native-console.py` is an executable manual harness for an authorized Windows host. It exercises actual mode setup/readback/restoration, navigation, explicit Ctrl+Enter, bounded fixed multiline paste and resize. It records no arbitrary typed text, never dispatches a Workbench command and cannot establish native application/platform approval. The operator must independently attest paste provenance; a programmatic event trace alone cannot prove clipboard origin. Run it in a NEW evidence directory with the full reviewed project:

```powershell
python -B scripts/qualify-native-console.py --project C:\reviewed\intune --output C:\evidence\console-NEW
```

The integrated Workspace and `run_terminal` both receive the exact native store. Unsupported native service/worker/mutation routes reject before dispatch until their own capabilities exist.

## Concrete shared engine proposal

The staged `workbench_tui.py.proposed.patch` adds an exact native binding to Workspace while preserving its current defaults. `workbench.py.proposed.patch` passes an exact native store through the existing `run_terminal`/dispatcher and requires a fixed readonly command allowlist before a native route can dispatch. `windows_workspace_binding.py` composes the exact store, context and console classes; it adds no CLI flag or host-profile activation. Native unsupported service/worker/mutation commands explicitly reject, while the complete parser/text interface stays shared.

Six local seam checks passed: ordinary Enter and modeled multiline paste do not submit edits, explicit submit does, default POSIX Enter stays functional, forged native binding/store is rejected, and actual shared dispatch denies unsupported native commands before action. The first test attempt incorrectly patched a nonexistent module-level collect; that setup error is retained, then corrected to observe the actual store.collect method.

All 16 existing Linux Workspace regressions passed through the staged shared modules and an actual staged CLI bootstrap, including real PTY, no-TTY fallback, resize, hostile text, bracketed paste, interruption and context reopen. The before/after source inventory was unchanged. These tests overlap prior UI evidence and do not establish any Win32 behavior. This receipt predates the reviewed shared-file integration recorded above.

## Reviewed route audit and final scoped replay

A source audit found the shared dictionary helper bypassed the native store's package reader. The failing-before test is preserved; the proposed helper now delegates only for the exact `WindowsWorkbenchStore`, retaining the unchanged POSIX path for ordinary stores. Overview/search/inspect/history/collections/health use the native store connection; raw inspection uses its native capture loader/parent; relationships use stored artifacts. `views` and `views-page` are explicitly excluded from this initial native profile because their local model/service journal reads have no admitted native reader. They remain available through the existing POSIX profile. No native journal compatibility is implied.

Eight route/input/shared-engine assertions pass after those repairs. Independent full composition passed seven assertions with exact binding/store/context/console classes and the real parser, engine and key reader, while native API calls were explicitly recorded models. It observed exactly collect(rejected), overview and quit, no mutation/collection rows, unchanged database, restored modes/handles and navigation reopen. Its first clipped-notice expectation failure is retained; no native platform result is inferred.

`windows-terminal-posix-02` correctly records a source-inventory failure while all 16 functional assertions passed: capture.py and observation_reader.py changed during that run. After the coordinated source freeze, `windows-terminal-posix-03/receipt.json` passed the same 16 checks with unchanged source inventory (SHA-256 `18a78ce6518cdad206595ede28f4f79daccaa77ba3297a4ae379cddcf5768620`). Exact source bytes are archived in that receipt directory. Counts overlap historical UI evidence.
