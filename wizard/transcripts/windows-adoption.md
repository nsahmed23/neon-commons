# Designed transcript — Windows PowerShell adoption (not host-recorded)

Developer: Adopt my existing policy without changing settings.
Wizard: I will first inspect the supplied local repository/export. This walkthrough uses synthetic data and will not authenticate or run Atmos.
Facts: engine tofu, provider candidate microsoft3651.0.0, reference-dev/intune-reference, two objects share a display name. Three assignments belong to the selected UUID, including an exclusion and an include-mode filter. Groups/filter/tag remain externally owned.
Question: Select the policy by UUID with its name as a label.
Developer: Select 22222222-2222-4222-8222-222222222222.
Question: Is the current writer this repo, another controller, or an adoption proposal only?
Developer: Proposal only; ownership transfer still needs review.
Wizard: Complete local snapshot; supported bounded mapping. I will write a new staging folder, not modify the current infrastructure repository.
Developer: Generate.
Wizard: Wrote main.tf, imports.tf, adoption-input.json, Atmos config/stack, field accounting, ID map and proposed command cards. Source IDs and all three target tuples match independent checks. Provider/tenant qualification has NOT occurred. The command renderer requires PowerShell7.3+; native Windows execution is not yet tested.
Developer: Show PowerShell commands.
Wizard: Shows commands/PROPOSED-import.ps1.txt in a powershell code block. Emit-only; no command executes. CLI import and import blocks are alternative approaches.
Developer: Save.
Wizard: Save fingerprints and decisions with no credentials/approval grants. First local implementation complete. The next remote step remains separately authorized.
