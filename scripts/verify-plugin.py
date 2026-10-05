#!/usr/bin/env python3
"""Run runtime tests and optionally the repaired core regressions."""
import argparse
import datetime
import io
import json
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


class ReleaseResult(unittest.TextTestResult):
    """Count complete top-level passes, not assertions or failed subtests."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.complete_passes = 0
        self.incomplete = set()

    def addSkip(self, test, reason):
        self.incomplete.add(getattr(test, 'test_case', test).id())
        super().addSkip(test, reason)

    def addSuccess(self, test):
        if test.id() not in self.incomplete:
            self.complete_passes += 1
        super().addSuccess(test)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--include-core',action='store_true')
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    suite=unittest.TestSuite()
    suite.addTests(unittest.defaultTestLoader.discover(str(ROOT/'plugin_tests'),pattern='test_*.py',top_level_dir=str(ROOT)))
    if args.include_core:
        suite.addTests(unittest.defaultTestLoader.discover(str(ROOT/'evaluations'),pattern='test_*.py'))
    stream=io.StringIO()
    planned=suite.countTestCases()
    result=unittest.TextTestRunner(stream=stream,verbosity=2,resultclass=ReleaseResult).run(suite)
    success=(planned > 0 and result.testsRun == planned
             and result.complete_passes == planned and result.wasSuccessful()
             and not result.skipped and not result.expectedFailures
             and not result.unexpectedSuccesses)
    report={'schema_version':'1.0.0','verified_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'tests':result.testsRun,'passed':result.complete_passes,'planned':planned,
            'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),
            'expected_failures':len(result.expectedFailures),'unexpected_successes':len(result.unexpectedSuccesses),
            'core_regressions_included':args.include_core,'success':success,
            'scope':'Local runtime behavior, repository semantics, negative contracts, synthetic and API-shaped capture pipelines, and HTTP protocol fixtures.',
            'not_established':['Live Graph authenticity or service semantics','Provider-backed import/no-change plan','Full native Atmos runtime configuration parity','Native Windows/PowerShell behavior','Native host installation','CLM learned-model quality, calibration or latency']}
    destination=Path(args.output);destination.mkdir(parents=True,exist_ok=True)
    (destination/'test-log.txt').write_text(stream.getvalue())
    (destination/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    return 0 if success else 1

if __name__=='__main__':raise SystemExit(main())
