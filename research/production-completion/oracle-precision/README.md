# Graph budget oracle precision correction

The earlier test patched `intune_iac.graph.digest`, while the hashing operation
had moved to `intune_iac.graph_validation.digest`. The budget rejection assertion
still ran, but the no-hashing assertion observed the wrong function.

The final source changes only that test target. A counterfactual injected early
hashing before the size guard: the old test passed incorrectly and the corrected
test failed. The corrected test passes on unchanged production code. Retained
logs and before/after hashes document this test repair. The final clean-extraction
suite covers the corrected file; the earlier integrated run predates it.
