Local provider repair candidate based on deploymenttheory/terraform-provider-microsoft365 v1.0.0, commit 1718c946b3ae111bb44c7c1d925b3e35b708cb0a. Modified provider source and additions are distributed under MPL-2.0; see LICENSE. This is an unpublished local engineering candidate. Its strict settings profile excludes secret settings rather than restoring secrets by array position. Full provider and service qualification statuses are reported separately in research/provider-qualification/completion-20261002/REPORT.md.

The 2026-10-04 source revision additionally repairs partial-create identity and
strict readback behavior and includes explicit go.mod/go.sum security updates.
`completion-manifest.json` records each original and replacement hash. Current
qualification is under the separately delivered epoch evidence; the older report
above remains historical. This directory does not alter or relabel the supplied
earlier binary, and does not grant production acceptance.
