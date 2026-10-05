# Active skill instruction review

Plugin Eval 0.1.2 measured the first 0.3.0 runtime candidate at 1,414 estimated invocation tokens: 259 for the manifest and 1,155 for the operational skill. That introduced a heavy-invocation warning. The skill was shortened by removing repeated prose and keeping detailed operation/recovery instructions in its existing linked documentation. Intake routes, explicit destinations, verify-before-success, blocked production candidates and authorization boundaries remain present.

The same evaluator then measured 1,171 invocation tokens, in its moderate band; trigger cost remained 118, in its good band. These are static estimates, not measured native host usage or behavioral benchmarks. The final exact-distribution report is delivered with the release receipt.

The evaluator also sums runtime Python/schema/documentation files into a deferred-text estimate. Those files remain necessary to execute local validation; the estimate is not evidence that the host actually reads them all into model context. Missing publisher website/privacy/terms URLs remain unresolved until an accountable publisher supplies real approved policies. The source distribution contains tests; the runtime intentionally does not. Remaining complexity and long functions are acknowledged rather than hidden by renaming or removing files.
