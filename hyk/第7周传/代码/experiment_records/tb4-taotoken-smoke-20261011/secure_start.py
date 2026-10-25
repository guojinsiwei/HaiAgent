import getpass
from pathlib import Path
import subprocess

print('Terminal-Bench 4.0 single task / KZ + DSH / TaoToken Token Plan')
print('Limits: 40 shared requests, 80 tools, 30 minutes. One task, no retries.')
print('Make sure plan credits remain: TaoToken can bill balance when credits run out.')
key = getpass.getpass('TaoToken API key (hidden, never saved): ').strip()
if not key:
    raise SystemExit('No key entered; nothing started.')
result = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15',
    '-i', 'C:/Users/54177/.ssh/cubestudio_notebook', 'lizh639@172.16.108.236',
    '/var/tmp/lizh639-tb4-taotoken-smoke-20261011/venv/bin/python',
    '/var/tmp/lizh639-tb4-taotoken-smoke-20261011/launch_remote.py'],
    input=(key + '\n').encode(), capture_output=True)
key = ''
message = (result.stdout + result.stderr).decode(errors='replace')
print(message)
Path(__file__).with_name('launch-receipt.txt').write_text(message, encoding='utf-8')
input('Press Enter to close...')
