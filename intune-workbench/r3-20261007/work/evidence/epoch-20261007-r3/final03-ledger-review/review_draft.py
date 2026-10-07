"""Receipt-only final03 ledger review; no product imports or test execution."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import subprocess

work=Path('/workspace/intune-continuation/work');epoch=work/'evidence/epoch-20261007-r3';draft=epoch/'final03-reconciliation';out=epoch/'final03-ledger-review/provisional-01'
out.mkdir(exist_ok=False)
checks=[];inputs={}
def h(data):return hashlib.sha256(data).hexdigest()
def get(path):
 data=path.read_bytes();inputs[str(path.relative_to(work))]={'bytes':len(data),'sha256':h(data)};return json.loads(data)
def check(name,value,details=None):checks.append({'name':name,'passed':bool(value),'details':details})
for p in draft.iterdir():
 if p.is_file():(out/p.name).write_bytes(p.read_bytes())
a=get(draft/'CONTINUATION-ACCEPTANCE-20261007-R3.json');idx=get(draft/'EVIDENCE-INDEX.json');failed=get(work/a['failed_final02_ledger']['path']);r2=get(work/a['prior_ledger']['path'])
current='289ee9477372825aad848f4482cf681c2ff43b02';prior='c122e38e33641336bc5af47b9dbf06eb0e58bc32';runtime='cce47f620f5e1e7d3dbdab1e030624fae3991cbf88376737a4eda07e6c703515'
check('exact_final03_authority',a['source_authority']['revision']==current and a['source_authority']['runtime']['sha256']==runtime)
check('failed_final02_ledger_embedded_unchanged',a['preserved_failed_final02_ledger']==failed and inputs[a['failed_final02_ledger']['path']]['sha256']==a['failed_final02_ledger']['sha256'])
check('R2_ledger_embedded_unchanged_and_hash_bound',a['preserved_prior_ledger']==r2 and failed['preserved_prior_ledger']==r2 and inputs[a['prior_ledger']['path']]['sha256']==a['prior_ledger']['sha256'])
check('nested_failed_final01_retained',failed['preserved_failed_final01_ledger']==get(work/failed['failed_final01_ledger']['path']))
r2strict=r2['feature_candidate']['strict_qualification'];check('exact_R2_1141_scope_untouched',r2['feature_candidate']['revision']=='74130d0db99febf2f41cf4f4ebe2920a5d4dffb7' and all(r2strict[k]==v for k,v in {'tests':1141,'passed':1141,'planned':1141,'failures':0,'errors':0,'skipped':0}.items()),r2strict)
refs=[e for row in a['rows'] for e in row.get('evidence',[])];bad=[]
for ref in idx['entries']:
 path=work/ref['path'];data=path.read_bytes()
 if len(data)!=ref['bytes'] or h(data)!=ref['sha256']:bad.append(ref['path'])
check('14_rows_33_direct_refs_34_indexed_refs',len(a['rows'])==14 and len(refs)==33 and len(idx['entries'])==34,{'direct_row_refs':len(refs),'indexed_refs':len(idx['entries']),'additional_index_ref':'Preserved failed-final02 ledger is the34th reference.'})
check('all_completed_indexed_refs_match_bytes',not bad,{'bad':bad})
indexed={e['path']:e for e in idx['entries']};check('all_row_refs_equal_indexed_refs',all(e==indexed[e['path']] for e in refs))
reuse=get(epoch/'milestone-0.8.0-final03/REUSED-QUALIFICATION-EVIDENCE.json');independent=get(epoch/'independent-artifact-reuse-final03/receipt.json')
check('byte_equivalence_independently_qualified',reuse['status']=='PASS_BYTE_EQUIVALENT_SCOPE_REUSE' and reuse['current_commit']==current and reuse['prior_commit']==prior and reuse['runtime_archive_byte_identical'] and reuse['application_grader_fixture_and_harness_files_unchanged'] and independent['status']=='PASS_BYTE_EQUIVALENT_SCOPE_REUSE' and len(independent['checks'])==428 and all(c['passed'] for c in independent['checks']) and len(independent['verified_hash_references'])==284 and independent['reviewed_root_reuse_proof_sha256']==inputs['evidence/epoch-20261007-r3/milestone-0.8.0-final03/REUSED-QUALIFICATION-EVIDENCE.json']['sha256'],{'independent_checks':len(independent['checks']),'verified_refs':len(independent['verified_hash_references']),'not_dynamic_tests':True})
changed=subprocess.check_output(['git','diff','--name-only',prior,current],cwd=work/'projects/intune',text=True).splitlines();check('actual_commit_only_reviewed_test_changed',changed==['plugin_tests/test_native_smoke_observation_epoch.py'],{'git_changed':changed,'archive_changed':reuse['source_archive_changed_paths']})
oldrows={r['requirement_id']:r for r in failed['rows']};reused=[r for r in a['rows'] if r['status']=='PASS_BY_EXACT_BYTE_EQUIVALENCE'];reusechecks=[]
for r in reused:
 original=oldrows[r['original_requirement_id']]
 reusechecks.append({'id':r['requirement_id'],'original_revision_preserved':r['source_revision']==r['observed_source_revision']==prior,'applicability_separate':r['applicable_source_revision']==current,'original_evidence_objects_preserved':all(e in r['evidence'] for e in original['evidence']),'runtime_exact':r['applicable_runtime_archive_sha256']==runtime,'reuse_hash':r['reuse_basis']['sha256']==inputs['evidence/epoch-20261007-r3/milestone-0.8.0-final03/REUSED-QUALIFICATION-EVIDENCE.json']['sha256']})
check('six_reused_scopes_keep_original_identities',len(reused)==6 and all(all(v for k,v in r.items() if k!='id') for r in reusechecks),reusechecks)
fresh=get(epoch/'milestone-0.8.0-final03/connected-source/receipt.json');pty=[v for v in fresh['commands'] if v.get('mode')=='actual_PTY'];check('fresh_source_journey_counts_match_raw',fresh['status']=='PASS' and len(fresh['checks'])==64 and len(fresh['commands'])==34 and len(pty)==10 and not fresh['source_changed_during_run'],{'checks':len(fresh['checks']),'commands':len(fresh['commands']),'pty':len(pty)})
rows={r['requirement_id']:r for r in a['rows']};final=epoch/'milestone-0.8.0-final03';gate_exists={p:(final/p).exists() for p in ('strict-suite/result.json','reproducibility.json','QUALIFICATION.json')};check('strict_and_repro_pending_without_completed_receipts',rows['R3-FINAL03-STRICT']['status']=='PENDING' and rows['R3-FINAL03-REPRODUCIBILITY']['status']=='PENDING' and not any(gate_exists.values()),gate_exists)
external={r['id']:r for r in a['external_prerequisites']};check('nine_external_gates_and_missing_implementation_explicit',len(external)==9 and all(all(r.get(k) for k in ('required_environment','authorization','procedure','expected_evidence','release_blocker')) for r in external.values()) and all(external[k]['class']=='MISSING_IMPLEMENTATION_AND_EXTERNAL_QUALIFICATION' for k in ('LIVE-EXECUTION-ADAPTER','INTEGRATED-AZURE-BACKEND')) and a['organizational_production_approval']=='NOT_GRANTED')
check('open_c122_actor_gap_not_closed_by_new_commit',rows['R3-COMMIT-TRANSITION-PROVENANCE']['status']=='OPEN_ACTOR_ATTRIBUTION' and rows['R3-COMMIT-TRANSITION-PROVENANCE']['source_revision']==prior and not rows['R3-COMMIT-TRANSITION-PROVENANCE']['source_or_archive_integrity_failure_inferred'])
checkpoint=(draft/'CHECKPOINT-20261007-R3.md').read_text();sequence=(draft/'EXECUTION-SEQUENCE-20261007-R3.md').read_text();check('historical_failures_discrepancies_and_replays_explicit',all(s in checkpoint for s in ('1,234','1,236','1,241','1,242','SEC-GAP-WORKSPACE-RESTART','original three','87 completed')) and all(s in sequence for s in ('scripts/verify-plugin.py --include-core','scripts/qualify-workbench-connected.py','qualify_capture_retry.py','qualify-workbench-capacity.py','native_smoke.py')))
for path in draft.iterdir():
 if path.is_file():
  data=path.read_bytes();check('draft_stable_'+path.name,data==(out/path.name).read_bytes());inputs[str(path.relative_to(work))]={'bytes':len(data),'sha256':h(data)}
report={'recorded_at':datetime.now(timezone.utc).isoformat(),'status':'PASS_PROVISIONAL_LEDGER_CONSISTENCY' if all(c['passed'] for c in checks) else 'REQUIRES_RECONCILIATION','source_commit':current,'inputs':inputs,'checks':checks,'pending_gates_at_review':gate_exists,'scope':'Read-only receipt/document/hash/commit-delta review. No source edits, product imports, test/native/CLI reruns, or new platform approval. Counts428/284 are independent artifact-review checks and refs, not strict tests.','followup':'Wait for actual final03 strict/repro/QUALIFICATION. Preserve this provisional receipt and append final review; never infer pass from reused runtime evidence.','documentation_note':'Native replay lists the recorded c122 commit explicitly. A future genuinely changed runtime must pass its own matching commit to the grader; preserved native observations must keep c122 identity.'}
(out/'REVIEW.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'status':report['status'],'checks':len(checks),'failed':[c['name'] for c in checks if not c['passed']],'pending':gate_exists,'receipt':str(out/'REVIEW.json')}))
