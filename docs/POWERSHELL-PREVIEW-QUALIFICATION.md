# PowerShell preview qualification

`reference/core.py:render_powershell` emits inactive command text. The generated
`commands/PROPOSED-import.ps1.txt` is not a runtime launcher. Its command card
requires `protected_ci_required` and sets `execution_allowed` to `false`.
Do not rename or execute a proposal as a substitute for protected execution.

The preview requires PowerShell 7.3 or later, uses single-quoted string values,
and requests Standard native argument passing. The exact argument `--%` is
unsupported: PowerShell 7.6.6 on Linux consumes it even inside a quoted splatted
array. The renderer rejects the entire proposal with an actionable error before
emitting text. It does not remove the argument or alter the requested operation.
Unicode single-quote delimiters U+2018 through U+201B are also unsupported.
Independent testing demonstrated that these delimiters could break out of the
old single-quoted preview and execute a local marker operation. The renderer now
rejects any value containing one before producing text. Existing
control-character, bidi-control, non-string, and executable-token
admission rules still apply. Nearby literal strings such as `--%%`, `x--%`, and
`--% ` remain distinct supported values.

Epoch 20261004 exercised the actual renderer on Linux AMD64 with official
PowerShell 7.6.6. The evaluator parsed the inactive import proposal without
dispatching it, then ran a separate harmless absolute Python argv/exit fixture
through the renderer. The earlier `run-04` passed 99 assertions, including exact argv
preservation for 42 supported literal values, reserved-token rejection, profile
and injection sentinels, exit-status propagation, malformed-parser rejection,
and inherited network denial. That revision preceded the independent
Unicode-single-quote finding, so its 99 passes do not qualify the final repair.
Forty focused/reference tests passed at that earlier revision. The
failing-before native transcript and three failing-before unit subcases remain
in `work/evidence/epoch-20261004/powershell-linux` in the delivery evidence.

After the Unicode-single-quote admission repair, independent checks passed for
12 plain unsupported-quote values and actual native argv preservation of ten
ordinary values, including normal Unicode and curly double quotes. See
`independent-review/powershell-literal-after/results.json`; it records the
renderer hash. Active adversarial after-effect verification remains incomplete:
automatic approval review rejected the proposed active marker/injection probe
for possible cybersecurity risk. The earlier independent marker probe had
already completed before that restriction was received and remains preserved.
No active after-payload was retried. Static rejection and ordinary-value replay
are not relabelled as an executed active after-effect test.

This is a narrow Linux parser/argv qualification. Windows PowerShell, native
Windows PowerShell 7, Git Bash/MSYS conversions, Windows ACLs, reparse points,
interactive host behavior, and supported-host installation/update qualification
remain separate requirements. No Intune, provider, backend, or tenant mutation
was performed by this evaluator.

Two evaluator starts failed while auto-loading `ConvertTo-Json` because
`System.Net.Http` could not be loaded; the root cause remains unresolved. The
preview itself uses no Utility-module cmdlet. Final evaluator reporting uses
built-in Console methods, with the same executable, socket-denial and resource
limits, to avoid that unrelated reporting dependency. Those failures prevent
claiming general-purpose PowerShell runtime qualification from this evidence.

The evaluator deliberately allows its fixed harmless native Python child. It is
not the protected product executor, whose no-new-process restriction is a
different boundary. No kernel filesystem isolation is claimed for this fixture.

The retained `powershell-linux/replay.py` describes the earlier broader fixture.
Its prior receipt is historical evidence, not authorization to repeat a rejected
active attack. For the permitted ordinary-literal continuation, use the separate
independent follow-up script
`work/evidence/epoch-20261004/independent-review/powershell_literal_followup.py`.
It uses a fixed output directory: copy it with a fresh output-directory name
before replay, retaining the original script and receipts unchanged.

The evidence checks all 580 runtime file hashes against the retained extraction
manifest. Acquisition URLs, official release metadata, checksum
manifest, MIT license, third-party notices, raw outputs, source hashes and
remaining limitations are in that evidence directory.

## Unicode quote boundary discovered during independent review

A subsequent actual Linux PowerShell 7.6.6 probe demonstrated that U+2018, U+2019, U+201A and U+201B can act as single-quote delimiters inside the emitted preview. The repaired renderer rejects any of these characters before returning a proposal, including in the executable value. Original marker effects are retained as negative evidence; no protected provider or tenant operation was involved. Plain Unicode text and curly double quotes remain separately checked as literal values.

A separate agent probe was automatically rejected for possible cybersecurity risk. Subsequent qualification is limited to static pre-emission rejection and harmless ordinary-text argv checks; the blocked probe is not counted as executed or passed. The original 99 checks preceded this additional repair and do not by themselves qualify the final renderer. Consult the final independent receipt and packaged-source test result.
