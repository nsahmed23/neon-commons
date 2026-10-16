#!/usr/bin/env python3
"""Relocatable plugin launcher. Installs nothing and never changes host config."""
import sys
from pathlib import Path

# LF-only output from the first byte: set before intune_iac.cli is imported, so even a traceback from a failed import is not
# turned into CRLF by a Windows text stream. cli.main() does the same for callers that do not come through here.
for _stream in (sys.stdout, sys.stderr):
    _reconfigure = getattr(_stream, 'reconfigure', None)
    if _reconfigure is not None:
        _reconfigure(newline='\n')

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from intune_iac.cli import main

if __name__ == '__main__':
    raise SystemExit(main())
