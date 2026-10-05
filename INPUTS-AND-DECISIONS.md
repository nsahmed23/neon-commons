# Inputs and decisions

Fixed: brownfield Intune technical-builder experience, OpenTofu enterprise engine, Atmos where present, Azure/Entra/Intune first-class, local generation and inspectable PowerShell/Bash commands, adoption separate from change, one writer, no silent field/target loss.

Reference choices: Python3.11+ source, JSON Schema2020-12, PowerShell7.3+ renderer, Linux Bash, Windows plain Settings Catalog/MDM policy, typed Deployment Theory provider1.0.0 as source-qualified candidate, Microsoft msgraph0.5.0 as comparison. No provider is organizationally approved by this dossier. Example engine/Atmos pins are explicit synthetic reference choices, not detected workstation versions.

Inspect actual repo inputs before real adaptation: provider source/lock, OpenTofu/Atmos executable/version, existing component/stack/backends, exporter format and relationship coverage, writer/ownership, target cloud/tenant/subscription, intended cohort, CI/approval and telemetry conventions. Supply only non-secret facts inside the approved environment. Do not upload tokens, state, raw sensitive exports or private keys here.

Input documents are retained unchanged under inputs/. Read the latest Appendix A/B goal where older prose emphasizes review rather than building. Old illustrative source locks and confidence labels are not evidence that code was downloaded or tests passed.
