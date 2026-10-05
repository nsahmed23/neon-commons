#!/usr/bin/env python3
"""Offline comparison of trusted expected and observed context, NOT signature validation."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from reference.approval import mismatches
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--expected',required=True);p.add_argument('--observed',required=True);p.add_argument('--as-of',required=True);a=p.parse_args()
x=mismatches(json.loads(Path(a.expected).read_text()),json.loads(Path(a.observed).read_text()),a.as_of)
print(json.dumps({'mismatches':x,'context_matches':not x,'approval_authenticated':False,'execution_authorized':False}))
raise SystemExit(2 if x else 0)
