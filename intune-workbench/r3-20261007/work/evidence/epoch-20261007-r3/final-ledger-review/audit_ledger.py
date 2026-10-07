"""Read-only receipt and draft consistency review. Never run product tests."""
import argparse
import hashlib
import json
from pathlib import Path
from datetime import datetime,timezone

parser=argparse.ArgumentParser();parser.add_argument('--work',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
work=args.work;epoch=work/'evidence/epoch-20261007-r3';final=epoch/'milestone-0.8.0-final01';draft=epoch/'final-reconciliation';out=args.output
out.mkdir(parents=True,exist_ok=False)
inputs={};checks=[]
def read(path):
 data=path.read_bytes();inputs[str(path.relative_to(work))]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()};return json.loads(data)
def check(name,passed,details=None):checks.append({'name':name,'passed':bool(passed),'details':details})
def all_pass(values):return all(v.get('passed') is True or v.get('pass') is True or v.get('status')=='PASS' for v in values)
for path in draft.iterdir():
 if path.is_file():
  data=path.read_bytes();(out/path.name).write_bytes(data);inputs[str(path.relative_to(work))]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
ledger=read(draft/'CONTINUATION-ACCEPTANCE-20261007-R3.json');checkpoint=(draft/'CHECKPOINT-20261007-R3.md').read_text();sequence=(draft/'EXECUTION-SEQUENCE-20261007-R3.md').read_text()
prior=read(work/ledger['prior_ledger']['path'])
check('R2_ledger_preserved_exact_semantics',ledger['preserved_prior_ledger']==prior)
check('R2_ledger_original_hash_unchanged',inputs[ledger['prior_ledger']['path']]['sha256']==ledger['prior_ledger']['sha256'])
r2=read(work/'evidence/epoch-20261005-r2/milestone-0.7.0/strict-suite/result.json')
check('R2_1141_exact_original_scope_retained',all(r2[k]==v for k,v in {'tests':1141,'passed':1141,'planned':1141,'failures':0,'errors':0,'skipped':0}.items()) and prior['feature_candidate']['strict_qualification']==r2, {'actual_original_result':r2,'rerun':False})
refs=[]
for row in ledger['rows']:
 for evidence in row.get('evidence',[]):
  p=work/evidence['path'];data=p.read_bytes();ok=len(data)==evidence['bytes'] and hashlib.sha256(data).hexdigest()==evidence['sha256'];refs.append({'requirement':row['requirement_id'],'path':evidence['path'],'match':ok})
check('all_current_row_evidence_hashes_and_sizes_match',all(v['match'] for v in refs),refs)
index=read(draft/'EVIDENCE-INDEX.json')
check('evidence_index_entries_match_bytes',all((work/v['path']).is_file() and len((work/v['path']).read_bytes())==v['bytes'] and hashlib.sha256((work/v['path']).read_bytes()).hexdigest()==v['sha256'] for v in index['entries']),{'entries':len(index['entries'])})
binding=read(final/'artifact-binding.json')
check('source_runtime_commit_and_archive_metadata_match',ledger['source_authority']['revision']==binding['commit'] and all(ledger['source_authority'][k]==binding[k] for k in ('source','runtime')) and binding['source_payloads_match_git'] and binding['archive_and_extracted_file_maps_match'],binding)
for label in ('source','runtime'):
 connected=read(final/('connected-'+label)/'receipt.json');pty=[v for v in connected['commands'] if v.get('mode')=='actual_PTY']
 check(label+'_connected_counts_and_negatives',connected['status']=='PASS' and len(connected['checks'])==64 and all_pass(connected['checks']) and len(connected['commands'])==34 and len(pty)==10 and all(v['terminal_attributes_restored'] for v in pty) and not connected['source_changed_during_run'],{'checks':len(connected['checks']),'commands':len(connected['commands']),'pty_sessions':len(pty)})
 capture=read(final/('capture-'+label)/'receipt.json')
 check(label+'_capture_counts_and_seam_scope',capture['success'] and len(capture['checks'])==59 and len(capture['commands'])==20 and all_pass(capture['checks']),{'checks':len(capture['checks']),'commands':len(capture['commands']),'scope':capture['scope']})
 capacity=read(final/('capacity-'+label)/'receipt.json')
 check(label+'_capacity_counts',capacity['status']=='PASS_SCOPED' and len(capacity['checks'])==10 and len(capacity['commands'])==48 and all_pass(capacity['checks']),{'checks':len(capacity['checks']),'commands':len(capacity['commands'])})
native=read(epoch/'native-codex-container/final-runtime-01/assertions.json')
check('native_codex_scoped_counts_and_exact_runtime',native['status']=='PASS_SCOPED' and native['passed']==26 and native['failed']==0 and native['native_commands']==10 and native['positive_native_commands']==9 and native['negative_native_commands']==1 and native['runtime_zip_sha256']==binding['runtime']['sha256'],{'scope':native['scope'],'remaining':native['remaining']})
security=read(epoch/'change-security-review/final-e8c581d/SECURITY-REVIEW.json')
check('security_inconclusive_not_certification',security['inventory_stable'] and security['file_count']==35 and security['raw_ast_candidate_count']==8 and not security['security_certified'] and not security['production_approved'])
cleanup=read(work/'evidence/epoch-20261005-r2/process-cleanup/qualification-summary.json');review=read(work/'evidence/epoch-20261005-r2/process-cleanup-review/review-receipt.json');link=read(epoch/'reconciliation/cleanup-evidence-linkage.json')
check('cleanup_before_after_and_unweakened_assertions',cleanup['before_original_test']['tests']==20 and cleanup['before_original_test']['failures']==9 and cleanup['original_test_unchanged'] and review['before']['case_count']==44 and review['before']['failed']==15 and review['after']['passed']==48 and review['after']['failed']==0 and review['original_test']['run']==20 and review['original_test']['failures']==0 and review['original_test']['unchanged_assertions'],{'root_cause_repair':'Leader exit/reap was insufficient evidence of descendant/task termination. waitid(WNOWAIT) retains group identity; bounded SIGKILL plus two complete per-task stable-identity censuses precede cleanup acknowledgment. Zombie leader does not imply terminal workers.','scope':cleanup['scope'],'original_before':cleanup['before_original_test'],'independent_before':review['before'],'independent_after':review['after'],'original_after':review['original_test']})
check('cleanup_raw_linkage_retained',all(hashlib.sha256((Path(link['evidence_base'])/k).read_bytes()).hexdigest()==v['sha256'] for k,v in link['artifacts'].items()))
check('three_historical_files_and_restart_not_silently_closed','three unexplained' in checkpoint and 'remain unresolved' in checkpoint and 'UNRESOLVED' in ledger['preservation']['working_cache'] and 'SEC-GAP-WORKSPACE-RESTART' in checkpoint)
rows={v['requirement_id']:v for v in ledger['rows']}
pending={'strict_result_exists':(final/'strict-suite/result.json').exists(),'reproducibility_exists':(final/'reproducibility.json').exists(),'qualification_exists':(final/'QUALIFICATION.json').exists()}
check('unfinished_final_gates_not_claimed_pass',rows['R3-080-STRICT']['status']=='PENDING' and rows['R3-FINAL-REPRODUCIBILITY']['status']=='PENDING',pending)
check('external_gates_have_complete_procedure_matrix',all(all(v.get(k) for k in ('required_environment','authorization','procedure','expected_evidence','release_blocker')) for v in ledger['external_prerequisites']),{'gates':len(ledger['external_prerequisites'])})
external={v['id']:v for v in ledger['external_prerequisites']}
check('missing_implementation_not_relabelled_credentials_only',all(external[k]['class']=='MISSING_IMPLEMENTATION_AND_EXTERNAL_QUALIFICATION' for k in ('LIVE-EXECUTION-ADAPTER','INTEGRATED-AZURE-BACKEND')) and ledger['organizational_production_approval']=='NOT_GRANTED')
check('explicit_replay_main_gates_present',all(s in sequence for s in ('scripts/verify-plugin.py --include-core','scripts/qualify-workbench-connected.py','qualify_capture_retry.py','scripts/qualify-workbench-capacity.py --prepare','scripts/qualify-workbench-capacity.py --run')))
corrections=[{'id':'DOC-CLEANUP-ANCHOR','severity':'documentation_completeness','requested':'Checkpoint should name the actual cleanup cause/repair and add the original20runs9fails→20/20 plus independent44cases15fails→48/48 linked evidence. Existing acceptance preserves these receipts; no repair rerun is warranted.','blocking_product_finding':False},{'id':'DOC-NATIVE-REPLAY','severity':'documentation_completeness','requested':'Sequence should link actual labs/production-lifecycle/native_smoke.py replay in final01/native.command.json and native Codex RESULT.md replay instructions; current generic table labels do not directly identify both procedures.','blocking_product_finding':False}]
corrections[0]['resolved_in_reviewed_draft'] = '44' in checkpoint and ('48/48' in checkpoint or 'passed all 48 expanded cases' in checkpoint) and 'waitid' in checkpoint and 'cleanup-evidence-linkage.json' in checkpoint
corrections[1]['resolved_in_reviewed_draft'] = 'native_smoke.py' in sequence and 'native-codex-container/RESULT.md' in sequence
check('requested_doc_clarity_changes_present',all(v['resolved_in_reviewed_draft'] for v in corrections))
report={'recorded_at':datetime.now(timezone.utc).isoformat(),'status':'PASS_SCOPED_DRAFT_REVIEW_WITH_DOCUMENTATION_REQUESTS' if all(c['passed'] for c in checks) else 'FAIL_REQUIRES_CORRECTION','source_commit':binding['commit'],'inputs':inputs,'checks':checks,'corrections_sent_to_owner':corrections,'limits':['Read-only review of frozen receipt contents and draft documentation; no product tests repeated.','Prior1141result retains its original exact0.7.0Linux scope; overlapping counts are not added.','Strict and reproducibility/final qualification were unfinished when review began; any newly completed receipt needs append-only follow-up.','No live Graph/native Intune/backend/device or organizational approval inferred.','Reviewer previously owned visibility and capacity repair; this is a ledger consistency review, not independent certification of that code.']}
(out/'REVIEW.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'status':report['status'],'checks':len(checks),'failed':[c['name'] for c in checks if not c['passed']],'pending_observed':pending,'receipt':str(out/'REVIEW.json')}))
