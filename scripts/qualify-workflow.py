#!/usr/bin/env python3
"""Exercise documented CLI workflow from outside the plugin directory."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--plugin',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();root=Path(args.plugin).resolve();dest=Path(args.output).resolve();dest.mkdir(parents=True,exist_ok=True)
    source=root/'examples/supported/input/export.json';context=root/'examples/context.json';cli=root/'scripts/intune-iac.py'
    records=[]
    with tempfile.TemporaryDirectory(prefix='intune-cli-') as td:
        td=Path(td);project=td/'project';state=td/'attempts';graph=td/'relationships.json'
        def run(name,arguments,expected=0):
            command=[sys.executable,str(cli),*map(str,arguments)]
            completed=subprocess.run(command,cwd=td,text=True,capture_output=True,timeout=30)
            record={'name':name,'arguments':list(map(str,arguments)),'exit_code':completed.returncode,'expected_exit':expected,'success':completed.returncode==expected}
            try:record['result']=json.loads(completed.stdout)
            except ValueError:record.update(success=False,diagnostic='non_json_output')
            records.append(record)
            return record.get('result',{})
        run('doctor',['doctor'])
        run('inspect',['inspect','--input',source,'--context',context])
        run('generate',['generate','--input',source,'--context',context,'--output',project,'--state-dir',state])
        run('verify',['verify','--input',source,'--context',context,'--output',project])
        run('graph_build',['graph','build','--input',source,'--context',context,'--atmos-root',project,'--output',graph,'--state-dir',state])
        assignments=run('assignments',['graph','query','--graph',graph,'--query','assignments'])
        placement=run('placement',['graph','query','--graph',graph,'--query','placement'])
        parameters=td/'parameters.json';parameters.write_text('{}')
        run('unknown_action',['action','preview','execute_shell','--parameters',parameters,'--state-dir',td/'unused-state'],3)
        invariants={'exclusion_preserved':any(n.get('target_type')=='exclusionGroupAssignmentTarget' for n in assignments.get('nodes',[])),
                    'placement_intent_visible':any(n.get('type')=='PlacementIntent' for n in placement.get('nodes',[])),
                    'unknown_action_no_state':not (td/'unused-state').exists()}
    result={'scope':'Documented local CLI flow, executed from unrelated working directory; not a behavioral model benchmark.',
            'checks':len(records)+len(invariants),'commands':records,'invariants':invariants,
            'success':all(r['success'] for r in records) and all(invariants.values())}
    (dest/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'success':result['success'],'checks':result['checks'],'invariants':invariants},indent=2))
    return 0 if result['success'] else 1

if __name__=='__main__':raise SystemExit(main())
