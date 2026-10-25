"""Read-only bash syntax validation on CubeStudio; never execute benchmark scripts."""
import json
from pathlib import Path
import shlex
import subprocess
root = Path(__file__).parent / 'upstream/tasks_long_cli'
scripts = {p.parent.name: p.read_text(encoding='utf-8') for p in root.glob('*/run-tests.sh')
           if p.parent.name != 'terminal-bench_task'}
code = """import json,sys,subprocess
for name,source in json.load(sys.stdin).items():
 p=subprocess.run(['bash','-n'],input=source,text=True,capture_output=True)
 print(json.dumps({'task':name,'syntax_ok':p.returncode==0,'diagnostic':p.stderr[:500]}))
"""
result = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
                         'cubestudio_container', 'python3 -c ' + shlex.quote(code)],
                        input=json.dumps(scripts), text=True, capture_output=True, timeout=45)
print(result.stdout)
print(result.stderr)
raise SystemExit(result.returncode)
