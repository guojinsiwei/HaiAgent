import os, json, subprocess, urllib.request, urllib.error
from pathlib import Path

print('HOST', os.uname().nodename)
active = []
for p in Path('/proc').iterdir():
    if not p.name.isdigit():
        continue
    try:
        args = (p / 'cmdline').read_bytes().split(b'\0')
        scripts = [a.decode(errors='replace') for a in args if a.endswith(b'.py')]
        if any(Path(a).name in ('run_comparison.py', 'run_notebook.py', 'run_agent.py', 'swe_batch.py') for a in scripts):
            active.append({'pid': p.name, 'scripts': scripts})
    except OSError:
        pass
print('ACTIVE', json.dumps(active))
root = Path('/mnt/lizh639/bestfgs-runs/swe100-paired-v2')
print('EXISTING_PROTOCOL', (root / 'comparison-protocol.json').exists())
keys = []
if os.environ.get('DEEPSEEK_API_KEY'):
    keys.append(('shell', os.environ['DEEPSEEK_API_KEY']))
tmux = '/mnt/lizh639/envs/bestfgs/bin/tmux'
result = subprocess.run([tmux, 'show-environment', '-g', 'DEEPSEEK_API_KEY'], capture_output=True, text=True)
if result.returncode == 0 and result.stdout.startswith('DEEPSEEK_API_KEY='):
    keys.append(('tmux', result.stdout.strip().split('=', 1)[1]))
seen = set()
for source, key in keys:
    if key in seen:
        continue
    seen.add(key)
    request = urllib.request.Request('https://api.deepseek.com/models', headers={'Authorization': 'Bearer ' + key.strip()})
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            payload = json.load(response)
            print('AUTH', source, response.status)
            print('MODELS', json.dumps([row.get('id') for row in payload.get('data', [])]))
    except urllib.error.HTTPError as exc:
        print('AUTH', source, exc.code)
    except Exception as exc:
        print('AUTH', source, type(exc).__name__)
if not keys:
    print('AUTH NO_KEY')
