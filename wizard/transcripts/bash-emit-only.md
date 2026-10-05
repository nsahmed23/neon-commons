# Designed transcript — Bash/CI emit-only (not host-recorded)

Developer: Generate an adoption proposal from this export with no prompts.
Wizard: Required inputs supplied: selected UUID, synthetic tenant, provider pin, component/stack, new output path. No environment authentication is attempted.
Local helper: Validates outer schema, each selected collection's coverage and every source-field pointer. Writes deterministic output to a new directory. stdout reports offline_mapping_complete=true, execution_authorized=false. Exit0 means local generation only.
Developer: Export Bash commands.
Wizard: Exports command cards and quoted Bash text. No eval, implicit installation, login or provider execution. A missing required input in unattended mode exits3 rather than waiting for input.
Developer: Run the same generation again.
Local helper: Same hashes and unedited files -> unchanged, exit0. No duplicates.
Developer: What happens in CI?
Wizard: Use the separate protected workflow reference only after approved identity/backend setup; ordinary PR checks have no cloud permissions. Compare approved file/revision/plan identity before any remote operation. This session does not dispatch CI.
