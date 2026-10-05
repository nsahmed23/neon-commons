# Reviewed dependency bytes

The tested install denominator is Linux x86_64, CPython 3.12. `requirements-runtime-linux-x86_64-cp312.lock` binds all ten runtime dependency versions to exact wheel SHA-256 values. `dependency-lock.json` records filenames, sizes, wheel metadata and the separately acquired PyPI JSON response hashes. Every selected wheel matched the corresponding PyPI file digest and size during acquisition. Index agreement is not publisher signature verification or a vulnerability assessment.

For this platform, acquire the wheels into a fresh directory, inspect them, then install into a fresh virtual environment:

```sh
python -m pip --isolated download --require-hashes --only-binary :all: --dest ./wheelhouse -r requirements-runtime-linux-x86_64-cp312.lock
python scripts/verify-dependencies.py --wheelhouse ./wheelhouse
python -m venv .venv
.venv/bin/python -m pip --isolated install --no-index --no-cache-dir --find-links ./wheelhouse --require-hashes --only-binary :all: -r requirements-runtime-linux-x86_64-cp312.lock
.venv/bin/python -m pip --isolated check
```

The read-only verifier requires exactly the locked regular wheel files, rejects changed hashes, duplicate/missing/extra members, unsafe archive paths and inconsistent package metadata, and never extracts or executes wheel code. Treat the lock as part of the reviewed release; someone who can replace both wheels and the lock can replace the trust root. Wheel installation and later imports execute trusted package code. Other Python/platform combinations need separately reviewed wheel sets and qualification; the un-hashed requirements files are version inventories, not equivalent integrity gates.

The fresh offline install, `pip check` and CLI doctor succeeded. The report is in `research/enterprise-dependencies/`. This does not cover native provider/Atmos/OpenTofu distribution provenance, host plugin installation, or organization-approved vulnerability policy.

On 2026-10-01, all ten exact locked versions were successfully queried against OSV and release-specific PyPI vulnerability metadata; neither returned an advisory for those versions. An uninstalled historical PyYAML 5.3.1 positive control returned known advisories. Raw requests, responses, timestamps and the denominator are retained in `research/enterprise-dependencies/vulnerability-assessment/`. This is a dated known-advisory lookup, not proof of vulnerability absence, continuous monitoring, or coverage of Python, OS, Go, native tools, provider dependencies or GitHub Action dependencies. Repeat the assessment under the organization's update policy before adoption.
