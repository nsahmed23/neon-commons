# Terraform corpus — exact declaration inventory, incomplete per-lab audit

The pinned `meta.yml` declares **88 paths**, counted from its actual contents, not a marketing count. `catalog-manifest.json` contains each declaration. Existence, lab IDs, requirements, effects, graders and attestation fields remain explicitly null because the individual files were not all retrieved. This is **not** closure of G12. No labs were run or solutions decrypted.

The re-fetched Terraform `conftest.py` at `86b69d2292485d179698f5b9bf648a29f935e216`, lines170–260, verifies instructor replay and its `LAB_NO_REPLAY=1`, `LAB_WORKDIR`, and `no_replay` exclusions. It also verifies a missing vault password can skip. Do not use root pytest as an agent score. The matching dsoxlab runner still requires separate source inspection.

`tools/inventory-catalog.py` accepts an already acquired checkout and exact expected commit, reads YAML and file names without importing or executing lab code, detects missing/extra/duplicate paths, and produces a metadata scan. It does not discover semantic effects from YAML alone; every result retains a manual-review requirement. Complete this separate workstream before claiming the full promised dossier, but do not delay offline adoption work on it.
