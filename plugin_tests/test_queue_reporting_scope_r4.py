"""Collection-wide counts must not hide missing policy-bound device reports."""
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

from intune_iac.synthetic import generate_estate
from intune_iac.modeled_service import ModeledService
from intune_iac.workbench_store import WorkbenchStore

ROOT = Path(__file__).resolve().parents[1]


class QueueReportingScopeTests(unittest.TestCase):
    def test_collection_success_does_not_remove_policy_reporting_findings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            estate = generate_estate(seed=924, policy_count=2)
            identities = [row['id'] for row in estate['truth']['policies']]
            service = ModeledService.create(root / 'service', estate['capture'], identities)
            store = WorkbenchStore.create(root / 'store', estate['truth']['tenant_id'])
            store.collect(service, deployment={'targeted':100,'reporting':100,'successful':100,'observed_at':time.time()})

            def queue():
                result = subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/intune-iac.py'),
                    'workbench', 'queue', '--root', str(store.root)], capture_output=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                return json.loads(result.stdout)['findings']

            rows = queue()
            reporting = {row['object_id'] for row in rows if row['finding'] == 'reporting_incomplete'}
            self.assertEqual(reporting, set(identities), 'A collection aggregate cannot satisfy either policy evidence gap')
            stamp = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
            document = {'schema_version':'workbench-device-evidence/1', 'tenant_id':store.tenant_id,
                'object_id':identities[0], 'evidence':{'schema_version':'1.0.0','synthetic':True,
                'as_of':stamp,'freshness_seconds':3600,
                'cohort':{'version':'fixture','eligible_ids':['device-1'],'targeted_ids':['device-1'],'excluded_ids':[]},
                'rows':[{'id':'report-1','device_id':'device-1','stage':'execution','status':'success','observed_at':stamp,
                         'source_file':'fixture.json','source_pointer':'/0','coverage':'complete','synthetic':True}],
                'capture':{'timezone':'UTC','clock_skew_seconds':None,'logging_enabled':None,'truncated':False,'access_errors':[]},
                'promotion_thresholds':{'min_reporting_ratio':1,'min_success_ratio':1}}}
            source = root / 'device.json'; source.write_text(json.dumps(document))
            imported = subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/intune-iac.py'), 'workbench',
                'device-evidence-import', '--root', str(store.root), '--input', str(source)], capture_output=True, timeout=10)
            self.assertEqual(imported.returncode, 0, imported.stderr)
            rows = queue()
            self.assertEqual({row['object_id'] for row in rows if row['finding'] == 'reporting_incomplete'}, {identities[1]})
            self.assertTrue(all(row['automatic_remediation'] is False for row in rows))


if __name__ == '__main__': unittest.main()
