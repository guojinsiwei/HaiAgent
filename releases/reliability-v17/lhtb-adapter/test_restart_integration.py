"""Zero-Docker, zero-API process restart drill in an isolated temporary directory."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

def await_true(check,seconds=30):
    until=time.monotonic()+seconds
    while time.monotonic()<until:
        if check(): return
        time.sleep(.1)
    raise AssertionError('Fixture deadline')

def main():
    source=Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory(prefix='lhtb-guard-fixture-') as tmp:
        root=Path(tmp)
        for name in ['durable.py','outcomes.py']: shutil.copy2(source/name,root/name)
        (root/'control.py').write_text('''import os,json,sys,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
METHODS=['raw']
PYTHON=sys.executable
def validate(): return {'protocol_sha256':'offline-fixture'}
def environment(): return dict(os.environ)
def cleanup_owned(root): pass
def execute(row,method):
    time.sleep(5)
    report=HERE/('trial-'+row['task'])/'result.json'
    (report.parent/'agent').mkdir(parents=True)
    (report.parent/'agent/audit.jsonl').write_text('')
    return {'task':row['task'],'method':method,'report':str(report),'verifier_result':{'rewards':{'score':0}},'exception_info':None,'process_exit_code':0}
''')
        (root/'prepare.py').write_text('''import json
def reserve(): pass
def write(path,value):
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(value)); tmp.replace(path)
''')
        (root/'prior-results.json').write_text('[]')
        (root/'manifest.json').write_text(json.dumps({'tasks':[{'task':'a'},{'task':'b'}]}))
        key=root/'fixture-key'; key.write_text('OFFLINE-NOT-A-REAL-KEY')
        command=[sys.executable,'-B',str(root/'durable.py'),'scheduler',str(key)]
        first=subprocess.Popen(command,cwd=root)
        second=None
        try:
            await_true(lambda:len(list((root/'ledger').glob('*/started.json')))==2)
            before=[json.loads(p.read_text())['pid'] for p in sorted((root/'ledger').glob('*/started.json'))]
            first.kill(); first.wait(timeout=5)
            second=subprocess.Popen(command,cwd=root)
            second.wait(timeout=35)
            health=json.loads((root/'health.json').read_text())
            after=[json.loads(p.read_text())['pid'] for p in sorted((root/'ledger').glob('*/started.json'))]
            assert before==after and health['state']=='completed' and health['completed']==2,health
            assert len(list((root/'ledger').glob('*/intent.json')))==2
            print(json.dumps({'restart_drill_passed':True,'same_trial_pids':True,'duplicate_launches':0,'completed':2,'real_model_calls':0}))
        finally:
            for p in [first,second]:
                if p and p.poll() is None: p.kill(); p.wait()
            for path in (root/'ledger').glob('*/started.json'):
                pid=json.loads(path.read_text())['pid']
                try: os.kill(pid,15)
                except ProcessLookupError: pass

if __name__=='__main__': main()
