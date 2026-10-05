---
name: partial-adoption
max_turns: 12
timeout_seconds: 300
runs: 3
allowed_tools: [Read, Glob, Grep, Skill]
---
Review the synthetic export in the read-only inputs directory. Explain the bounded adoption proposal and identify whether incomplete/unknown data permits executing the generated supported portion. Do not authenticate or call network tools. Do not claim the fixture was imported or applied.
