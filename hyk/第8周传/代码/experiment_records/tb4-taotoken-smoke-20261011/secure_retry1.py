import getpass
import hashlib
import json
from pathlib import Path
import subprocess

print('DSH + KZ -> TaoToken: live chain gate, then ONE Terminal-Bench task.')
print('Gate: at most 8 requests. Task: unchanged 40 requests / 80 tools / 30 min.')
print('Old results preserved. No automatic retries. Key remains in memory only.')
key=getpass.getpass('TaoToken API key (hidden): ').strip()
if not key: raise SystemExit('Empty input: nothing started')
payload=json.dumps({'key':key,'input_sha256':hashlib.sha256(key.encode()).hexdigest()})+'\n'
result=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=15',
    '-i','C:/Users/54177/.ssh/cubestudio_notebook','lizh639@172.16.108.236',
    '/var/tmp/lizh639-tb4-taotoken-smoke-20261011/venv/bin/python',
    '/var/tmp/lizh639-tb4-taotoken-smoke-20261011/launch_retry1.py'],input=payload.encode(),capture_output=True,timeout=40)
output=(result.stdout+result.stderr).decode(errors='replace').replace(key,'[REDACTED]')
key='';payload=''
print(output)
Path(__file__).with_name('retry1-launch-receipt.txt').write_text(output,encoding='utf-8')
input('Press Enter to close...')
