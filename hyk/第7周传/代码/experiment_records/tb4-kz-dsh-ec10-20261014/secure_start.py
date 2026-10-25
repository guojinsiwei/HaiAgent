import getpass,json,subprocess,time,shlex,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
REMOTE='/var/tmp/lizh639-tb4-kz-dsh-ec10-20261014'
PY='/var/tmp/lizh639-tb4-taotoken-smoke-20261011/venv/bin/python'
SSH=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=15','-i','C:/Users/54177/.ssh/cubestudio_notebook','lizh639@172.16.108.236']
def status(state,**fields):
    (ROOT/'secure-input-status.json').write_text(json.dumps(dict(state=state,time=time.time(),pid=os.getpid(),**fields)),encoding='utf8')
def main():
    code="import sys;from pathlib import Path;sys.path.insert(0,"+repr(REMOTE)+");import runner;r=runner.validate();assert r.get('official_installation_and_grading') and r.get('ten_task_fault_simulation');assert not (runner.ROOT/'launch-once.marker').exists();print('READY')"
    r=subprocess.run(SSH+[PY+' -c '+shlex.quote(code)],capture_output=True,timeout=60)
    if r.returncode or b'READY' not in r.stdout:
        status('precheck_failed');raise SystemExit('Precheck failed. Do not input a key.')
    if '--check-only' in sys.argv:print('READY');return
    print('KZ + DSH 0.3.0: 10 fixed TerminalBench tasks. First task is the pilot, then two concurrent.')
    print('No request/tool/cost cap; 3-hour server deadline per task. Existing DSH experiments unchanged.')
    status('ready_for_key');key=getpass.getpass('TaoToken API key (hidden): ').strip()
    if not key:raise SystemExit('Empty key, not started.')
    try:
        status('submitting');r=subprocess.run(SSH+[PY,REMOTE+'/runner.py','--launch'],input=(json.dumps({'key':key})+'\n').encode(),capture_output=True,timeout=60)
        output=(r.stdout+r.stderr).decode(errors='replace').replace(key,'[REDACTED]')
    finally:key=''
    (ROOT/'launch-receipt.txt').write_text(output,encoding='utf8');print(output)
    status('launch_acknowledged' if r.returncode==0 else 'launch_unconfirmed',returncode=r.returncode)
    input('Press Enter to close...')
if __name__=='__main__':main()
