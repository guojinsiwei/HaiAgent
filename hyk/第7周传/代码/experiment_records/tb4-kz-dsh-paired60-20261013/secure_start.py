import getpass,json,subprocess,time,shlex,sys,os
from pathlib import Path
ROOT=Path(__file__).resolve().parent
REMOTE='/var/tmp/lizh639-tb4-kz-dsh-paired60-20261013'
PYTHON='/var/tmp/lizh639-tb4-taotoken-smoke-20261011/venv/bin/python'
SSH=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=15','-i','C:/Users/54177/.ssh/cubestudio_notebook','lizh639@172.16.108.236']
def status(state,**fields):
    (ROOT/'secure-input-status.json').write_text(json.dumps(dict(state=state,time=time.time(),pid=os.getpid(),**fields)),encoding='utf-8')
def check_ready():
    status('checking_server')
    code="import sys;sys.path.insert(0,"+repr(REMOTE)+");from runner import validate;validate();print('READY')"
    # SSH joins arguments into a remote shell command: quote the Python program.
    result=subprocess.run(SSH+[PYTHON+' -c '+shlex.quote(code)],capture_output=True,timeout=45)
    if result.returncode or b'READY' not in result.stdout:
        status('precheck_failed',returncode=result.returncode)
        (ROOT/'precheck-receipt.txt').write_text((result.stdout+result.stderr).decode(errors='replace'),encoding='utf-8')
        raise SystemExit('SERVER PRECHECK FAILED. Do not enter a key. Close this window.')
    status('ready_for_key');return True
def main():
    if '--check-only' in sys.argv:
        check_ready();status('precheck_verified');print('READY: local SSH quoting and remote acceptance verified. No key collected.');return
    print('TerminalBench 4.0: KZ+DSH versus DSH, same frozen 30 tasks (60 trials).')
    print('Per task: 800 total requests, 600 tools, 2h, 1M context, 32768 output.')
    print('50 CNY historical estimate guard is NOT a TokenPlan balance guarantee.')
    print('First pair pilot, then 4 concurrent total. No automatic paid reruns.')
    check_ready()
    key=getpass.getpass('TaoToken API key (hidden): ').strip()
    if not key:raise SystemExit('Empty key, nothing started.')
    try:
        status('submitting')
        result=subprocess.run(SSH+[PYTHON,REMOTE+'/runner.py'],input=(json.dumps({'key':key})+'\n').encode(),capture_output=True,timeout=45)
        output=(result.stdout+result.stderr).decode(errors='replace').replace(key,'[REDACTED]')
    finally:key=''
    print(output);(ROOT/'launch-receipt.txt').write_text(output,encoding='utf-8')
    if result.returncode:
        status('launch_not_confirmed',returncode=result.returncode)
        raise SystemExit('Launch not confirmed. Do not blindly retry; inspect receipt.')
    status('launch_acknowledged')
    print('Server holds the run independently. Closing this window or powering off the PC will not stop it.')
    input('Press Enter to close...')
if __name__=='__main__':main()
