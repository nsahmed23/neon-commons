#!/usr/bin/env python3
"""Exercise the real wizard in a Linux PTY and save the observed transcript."""
import argparse
import json
import os
from pathlib import Path
import pty
import select
import subprocess
import sys
import tempfile
import time


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plugin',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();root=Path(args.plugin).resolve();dest=Path(args.output).resolve();dest.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='intune-pty-') as td:
        session=Path(td)/'session.json';generated=Path(td)/'project'
        command=[sys.executable,str(root/'scripts/intune-iac.py'),'wizard','--session',str(session),
                 '--input',str(root/'examples/supported/input/export.json'),'--context',str(root/'examples/context.json'),'--output',str(generated)]
        master,slave=pty.openpty()
        process=subprocess.Popen(command,stdin=slave,stdout=slave,stderr=slave,cwd=td,close_fds=True)
        os.close(slave);transcript=b'';sent_generate=False;sent_finish=False;deadline=time.monotonic()+30
        try:
            while time.monotonic()<deadline:
                ready,_,_=select.select([master],[],[],0.2)
                if ready:
                    try:chunk=os.read(master,65536)
                    except OSError:break
                    if not chunk:break
                    transcript+=chunk
                    text=transcript.decode('utf-8',errors='replace')
                    if not sent_generate and 'Preview [' in text:
                        os.write(master,b'generate\n');sent_generate=True
                    if not sent_finish and 'Review [' in text:
                        os.write(master,b'finish\n');sent_finish=True
                if process.poll() is not None:break
            if process.poll() is None:process.kill()
            status=process.wait(timeout=5)
        finally:os.close(master)
        verification=subprocess.run([sys.executable,str(root/'scripts/intune-iac.py'),'verify','--input',str(root/'examples/supported/input/export.json'),'--context',str(root/'examples/context.json'),'--output',str(generated)],capture_output=True,text=True)
        result={'scope':'Linux PTY only; no native Windows or host UI qualification','exit_code':status,
                'generate_sent':sent_generate,'finish_sent':sent_finish,'verify_exit_code':verification.returncode,
                'success':status==0 and sent_generate and sent_finish and verification.returncode==0}
        (dest/'transcript.txt').write_bytes(transcript)
        (dest/'result.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result,indent=2))
        return 0 if result['success'] else 1

if __name__=='__main__':raise SystemExit(main())
