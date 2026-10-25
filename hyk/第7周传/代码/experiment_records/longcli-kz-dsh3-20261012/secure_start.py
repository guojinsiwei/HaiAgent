"""Visible local hidden-input entry; key exists only in memory and SSH stdin."""
import getpass
import json
from pathlib import Path
import subprocess
import time

ROOT=Path(__file__).resolve().parent
REMOTE='/var/tmp/lizh639-longcli-kz-dsh3-20261012/'
PYTHON='/var/tmp/lizh639-tb4-taotoken-smoke-20261011/venv/bin/python'
SSH=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=15','-i','C:/Users/54177/.ssh/cubestudio_notebook','lizh639@172.16.108.236']

def main():
    print('CURRENT DSH + KZ: hog, cats, ap35. Historical KZ comparison; NOT TerminalBench.')
    print('Per task: 800 shared requests / 600 tools / 2h / 1M context / 32768 output.')
    print('One pilot then up to 2 concurrent. Fresh container/home/memory for every task.')
    print('Historical cost-estimate guard 50 CNY/task; not a TokenPlan balance meter.')
    print('No API key saved; no automatic paid retries; no GPT-funded monitoring.')
    key=getpass.getpass('TaoToken API key (hidden): ').strip()
    if not key:raise SystemExit('Empty input; nothing started.')
    payload=(json.dumps({'key':key})+'\n').encode()
    try:
        result=subprocess.run(SSH+[PYTHON,REMOTE+'runner.py'],input=payload,capture_output=True,timeout=45)
        output=(result.stdout+result.stderr).decode(errors='replace').replace(key,'[REDACTED]')
    finally:key='';payload=b''
    print(output);(ROOT/'launch-receipt.txt').write_text(output,encoding='utf-8')
    if result.returncode:raise SystemExit('Launch not confirmed. Inspect receipt; do not auto-retry.')
    print('Launched. This window now retrieves PUBLIC status only; closing it will not stop the server.')
    while True:
        try:
            result=subprocess.run(SSH+[PYTHON,REMOTE+'status.py'],capture_output=True,timeout=35)
            if result.returncode:print('Status temporarily unavailable; not evidence of termination.')
            else:
                data=json.loads(result.stdout)
                (ROOT/'latest-status.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
                print(time.strftime('%H:%M:%S'),data['state'],[(x['task'],x['state'],x.get('api_attempts'),x.get('score')) for x in data['tasks']],flush=True)
                if data['state'] in ('complete','needs_attention'):
                    print('Campaign ended. Results are saved in latest-status.json.');break
        except (OSError,ValueError,subprocess.TimeoutExpired):print('Status check unavailable; next read in 30s.')
        time.sleep(30)
    input('Press Enter to close...')

if __name__=='__main__':main()
