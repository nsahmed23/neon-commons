# Intune-to-IaC Wizard — Research Handoff

This folder contains the four requested research documents for the interactive brownfield Intune-to-IaC wizard. Read them in the numbered order below.

## Documents and purposes

| Order | Document | Purpose |
|---|---|---|
| 1 | [v3 research brief](01_V3_Research_Brief.md) | The full engineering scope and constraints. |
| 2 | [Completed v3 report](02_V3_Completed_Report.md) | Architecture and upstream reuse decisions. |
| 3 | [Appendix A research brief](03_Appendix_A_Research_Brief.md) | The interactive terminal-wizard requirements and required deliverables. |
| 4 | [Completed Appendix A report](04_Appendix_A_Completed_Report.md) | Implementation approach, data contracts, source leads, and build sequence. |

## How to use this handoff

Give all four documents to the computer-access builder together. The later Appendix A requirements clarify the product: an interactive technical builder that starts with existing Intune configuration and generates maintainable OpenTofu/Atmos IaC, supporting Azure workflows, and inspectable PowerShell/Bash commands. Earlier architecture proposals should be read in that context.

This is a **research-document bundle**, not the finished plugin, a source-code implementation, or a claim that the proposed build-materials dossier has already been fully populated. The reports retain their original limitations, unverified examples, and remaining build/qualification tasks. Packaging these documents does not authorize tenant authentication, state imports, deployments, endpoint collection, or other live operations.

## Preservation and source links

The two research briefs are byte-for-byte copies of their original Markdown files. The complete final-report text was extracted from each saved research report, without rewriting its prose, tables, diagrams, or code blocks. ChatGPT citation markers were converted to Markdown footnotes using the source links stored with those reports.

The v3 report contains 12 distinct internal file citations for which its export supplies no resolvable source URL. They are explicitly marked in its source notes rather than silently removed or replaced with guessed links. The Appendix A report's citation links were all available in its export. Technical claims and link availability were not rechecked during packaging.

`SHA256SUMS.txt` contains integrity hashes for the four documents and this README. The ZIP was checked for readable contents, matching hashes, and safe relative paths.

Packaged: September 30, 2026.
