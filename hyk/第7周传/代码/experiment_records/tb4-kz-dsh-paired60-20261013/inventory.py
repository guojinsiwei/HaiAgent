"""Read public task metadata only. No test/oracle material enters model input."""
import json
from pathlib import Path
import subprocess
import tomllib

REPO = Path('/var/tmp/lizh639-tb4-taotoken-smoke-20261011/terminal-bench')
COMMIT = '452bf305c6daa62fc59061d22133a7cbc7c1572e'
def git(*args):
    return subprocess.check_output(['git', '-C', str(REPO), *args])

def main():
    paths = git('ls-tree', '-r', '--name-only', COMMIT, 'tasks').decode().splitlines()
    rows = []
    for path in paths:
        if path.count('/') == 2 and path.endswith('/task.toml'):
            data = tomllib.loads(git('show', f'{COMMIT}:{path}').decode())
            rows.append(dict(name=path.split('/')[1], task=data.get('task'), metadata=data.get('metadata'),
                             agent=data.get('agent'), verifier=data.get('verifier'), environment=data.get('environment')))
    result = dict(commit=COMMIT, tasks=rows)
    (Path(__file__).parent/'inventory.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False))

if __name__ == '__main__': main()
