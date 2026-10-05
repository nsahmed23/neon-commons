#!/usr/bin/env python3
"""Relocatable plugin launcher. Installs nothing and never changes host config."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from intune_iac.cli import main

if __name__ == '__main__':
    raise SystemExit(main())
