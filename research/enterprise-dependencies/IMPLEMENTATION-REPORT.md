# Dependency integrity implementation

Ten exact runtime wheels were matched to independently retrieved PyPI JSON filenames, SHA-256 values and sizes. Raw index responses, their hashes and wheel metadata are recorded. A fresh CPython3.12 virtual environment installed all ten with `--isolated --no-index --no-cache-dir --require-hashes --only-binary :all:`; pip check and the real CLI doctor passed. No runtime requirements changed.

`verify-dependencies.py` is read-only and checks exact bounded inventory, bytes and package metadata without extraction. Five adversarial tests cover changed bytes, missing/extra wheels, inconsistent name/version, duplicate metadata/lock records, unsafe archive paths and symlinks. Independent security review found no counterexample in the stated scope.

The CycloneDX1.6 inventory lists dependency artifacts only; it does not assert a resolved transitive graph or include the Python interpreter/provider/tool executables. These are reproducibility and integrity controls, not a vulnerability scan or signed publisher attestation. Locks are a reviewed release trust root. Windows, macOS and different Python ABI wheels remain unqualified.

Primary references: https://pip.pypa.io/en/stable/topics/secure-installs/ and https://packaging.python.org/en/latest/specifications/binary-distribution-format/. No code copied from either source.

A later bounded known-advisory lookup is separately recorded in `vulnerability-assessment/`: all ten exact versions were queried against OSV and release-specific PyPI data on 2026-10-01, with zero returned runtime advisory IDs and a successful historical positive control. That assessment does not change the earlier installation receipt or turn the wheel verifier into a vulnerability scanner. Database coverage and freshness limits remain explicit.
