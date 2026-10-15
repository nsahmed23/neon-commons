#!/usr/bin/env bash
# Builds the pre-upgrade artefacts that plugin_tests/fixtures/pre_pin_migration freezes.
# Usage: bash GENERATE.sh WORKTREE PYTHON
#   WORKTREE: a checkout of commit 5d709ba (the last commit before the pin migration)
#   PYTHON:   the interpreter that runs the product (CPython 3.12 on Linux)
# SYNTHETIC data only, no network. Everything is built under the fixed root below because the session,
# journey and adoption evidence bind absolute paths and digests of files that contain them.
# Only the product's own entry points are used: scripts/intune-iac.py generate, wizard, wizard --journey,
# synthetic generate, workbench init and workbench adopt.
set -u
WT=$1
PY=$2
F=/tmp/pre-pin-freeze
CLI=$WT/scripts/intune-iac.py
export PYTHONDONTWRITEBYTECODE=1
rm -rf "$F"
mkdir -p "$F/inputs" "$F/contexts" "$F/projects" "$F/logs" "$F/work"
cd /tmp || exit 1

# 1. Inputs and contexts. examples/context.json and examples/supported/input/export.json are copied as they are.
cp "$WT/examples/supported/input/export.json" "$F/inputs/synthetic-export.json"
cp "$WT/examples/context.json" "$F/contexts/synthetic-explicit-pins.context.json"
# The production path needs a non-synthetic plugin capture and a context with source_is_synthetic false.
# These edits are the ones plugin_tests/test_production.py inputs() makes.
"$PY" -B - "$WT" "$F" <<'PYEOF'
import json, sys
wt, f = sys.argv[1], sys.argv[2]
src = json.load(open(wt + '/examples/supported/input/export.json'))
src['synthetic'] = False
src['exporter'] = {'id': 'intune-iac-settings-catalog-graph', 'version': '1.0.0'}
src['references'] = []
src['ownership'] = []
policy = src['collections'][0]['pages'][0]['body']['value'][0]
policy.update(creationSource='portal', priorityMetaData=None, templateReference=None, disableEntraGroupPolicyAssignment=False)
for a in src['collections'][2]['pages'][0]['body']['value']:
    a.update(source='direct', sourceId=None)
open(f + '/inputs/production-export.json', 'w').write(json.dumps(src, indent=2, sort_keys=True) + '\n')
ctx = json.load(open(wt + '/examples/context.json'))
ctx.update(source_is_synthetic=False, component='windows-privacy', stack='workstation-pilot')
open(f + '/contexts/production-explicit-pins.context.json', 'w').write(json.dumps(ctx, indent=2) + '\n')
PYEOF

# 2. A saved repository wizard session, stopped at the preview step before generation. The wizard writes the
#    repository context itself (wizard.py _repository_context): no engine, atmos or provider pins in it.
S=$F/session
mkdir -p "$S/repository/stacks/deploy" "$S/repository/components/terraform/policy"
printf '%s\n' 'base_path: .' 'stacks:' '  base_path: stacks' "  included_paths: ['deploy/**/*']" 'components:' '  terraform:' '    base_path: components/terraform' > "$S/repository/atmos.yaml"
printf '%s\n' 'vars:' '  region: west' 'components:' '  terraform:' '    policy:' '      vars:' '        stage: dev' > "$S/repository/stacks/deploy/dev.yaml"
: > "$S/repository/components/terraform/policy/.gitkeep"
cp "$F/inputs/production-export.json" "$S/export.json"
printf '%s\n' deploy/dev policy 22222222-2222-4222-8222-222222222222 save | "$PY" -B "$CLI" wizard --session "$S/session.json" --repo "$S/repository" --input "$S/export.json" --output "$S/project" > "$F/logs/session-wizard.out" 2>&1
echo "session wizard rc=$?"
cp "$S"/session.json.repository-context.*.json "$F/contexts/repository-omitted-pins.context.json"

# 3. Projects: what production generates from each context, and what the synthetic path generates.
"$PY" -B "$CLI" generate --input "$F/inputs/synthetic-export.json" --context "$F/contexts/synthetic-explicit-pins.context.json" --output "$F/projects/synthetic-explicit-pins" --state-dir "$F/work/attempts-synthetic" > "$F/logs/generate-synthetic.out" 2>&1
echo "generate synthetic rc=$?"
"$PY" -B "$CLI" generate --input "$F/inputs/production-export.json" --context "$F/contexts/production-explicit-pins.context.json" --output "$F/projects/production-explicit-pins" --state-dir "$F/work/attempts-production-explicit" > "$F/logs/generate-production-explicit.out" 2>&1
echo "generate production explicit rc=$?"
"$PY" -B "$CLI" generate --input "$F/inputs/production-export.json" --context "$F/contexts/repository-omitted-pins.context.json" --output "$F/projects/production-omitted-pins" --state-dir "$F/work/attempts-production-omitted" > "$F/logs/generate-production-omitted.out" 2>&1
echo "generate production omitted rc=$?"

# 4. A completed synthetic journey (one policy). The WSL clock sometimes steps backward and the journey then stops
#    with clock_moved_backward; the whole journey is rebuilt from nothing until one run completes.
J=$F/journey
for attempt in 1 2 3 4 5 6; do
  rm -rf "$J"
  mkdir -p "$J"
  "$PY" -B "$CLI" synthetic generate --output "$J/synthetic" --seed 721 --policies 1 > "$F/logs/synthetic-generate.out" 2>&1
  printf '%s\n' continue continue continue 10bd368c-bef5-5691-8fd4-235ab85f70b4 continue continue continue continue generate continue continue plan approve execute reconcile continue finish \
    | "$PY" -B "$CLI" wizard --journey --session "$J/session.json" --input "$J/synthetic/capture.json" --context "$J/synthetic/context.json" --output "$J/output" > "$F/logs/journey-wizard.out" 2>&1
  lifecycle=$("$PY" -B -c "import json,sys;print(json.load(open(sys.argv[1]))['lifecycle'])" "$J/session.json")
  echo "journey attempt=$attempt lifecycle=$lifecycle"
  if [ "$lifecycle" = complete_simulation ]; then break; fi
done

# 5. The adoption handoff of that journey into a new observation store.
A=$F/adoption
mkdir -p "$A"
TENANT=$("$PY" -B -c "import json,sys;print(json.load(open(sys.argv[1]))['tenant_id'])" "$J/synthetic/context.json")
"$PY" -B "$CLI" workbench init --root "$A/store" --tenant "$TENANT" > "$F/logs/workbench-init.out" 2>&1
echo "workbench init rc=$?"
"$PY" -B "$CLI" workbench adopt --root "$A/store" --session "$J/session.json" --output "$A/handoff" > "$F/logs/workbench-adopt.out" 2> "$F/logs/workbench-adopt.err"
echo "workbench adopt rc=$?"
