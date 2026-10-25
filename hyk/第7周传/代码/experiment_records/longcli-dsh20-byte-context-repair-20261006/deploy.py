"""Public files only; binary SSH stream transports the frozen runtime, no keys."""
import argparse
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent
KEY = 'C:/Users/54177/.ssh/cubestudio_notebook'
COLLEGE = ['ssh', '-i', KEY, '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15', 'lizh639@172.16.108.236']
REMOTE = '/mnt/lizh639/' + ROOT.name
PROXY = 'ProxyCommand=ssh -i ' + KEY + ' -o BatchMode=yes -o ConnectTimeout=15 -W %h:%p lizh639@172.16.108.236'
PYTHON = '/mnt/lizh639/envs/swe-eval/bin/python'


def cube(worker):
    return ['ssh', '-i', KEY, '-p', str((31081, 31121)[worker]), '-o', 'BatchMode=yes',
            '-o', 'ConnectTimeout=15', '-o', PROXY, 'root@172.16.108.241']


def main(worker, revision=1):
    if worker == 0:
        if revision == 1:
            subprocess.run(cube(worker) + ['mkdir ' + REMOTE], check=True, timeout=30)
            subprocess.run(cube(worker) + ['cp -a --reflink=auto /mnt/lizh639/longcli-dsh20-matched-20261005/runtime ' + REMOTE + '/runtime'],
                           check=True, timeout=600)
        else:
            # Only ended keyless revisions may be superseded. Keep their
            # public source snapshot and receipts; never touch a launched run.
            check = ("from pathlib import Path; import json; p=Path('" + REMOTE + "'); "
                     "assert not list(p.glob('launch-*.claim')); "
                     "assert all(json.loads(f.read_text()).get('state') not in ('preparing','running') "
                     "for f in p.glob('acceptance-jobs/*/health.json'))")
            import shlex
            subprocess.run(cube(worker) + [PYTHON + ' -c ' + shlex.quote(check)], check=True, timeout=30)
            archive = f'source-pre-r{revision}.tar'
            subprocess.run(cube(worker) + ['cd ' + REMOTE + ' && test ! -e ' + archive +
                           ' && tar -cf ' + archive + ' -- *.py *.mjs *.yml *.txt'], check=True, timeout=60)
    else:
        subprocess.run(cube(worker) + ['test -f ' + REMOTE + '/runtime/dsh/node_modules/@deepseek-ai/dsh/lib/bin.js'], check=True, timeout=30)
    files = [p for p in ROOT.iterdir() if p.suffix in ('.py', '.mjs', '.yml', '.txt')]
    subprocess.run(['scp', '-i', KEY, '-P', str((31081, 31121)[worker]), '-o', 'BatchMode=yes', '-o', PROXY,
                    *map(str, files), 'root@172.16.108.241:' + REMOTE + '/'], check=True, timeout=120)
    result = subprocess.run(cube(worker) + [f'{PYTHON} -B {REMOTE}/prepare.py --worker {worker} --revision {revision}'], timeout=1000)
    assert result.returncode == 0, 'Keyless acceptance failed; no paid run permitted'
    for name in (f'acceptance-{worker}-r{revision}.json', 'protocol.json', f'ready-{worker}.json'):
        subprocess.run(['scp', '-i', KEY, '-P', str((31081, 31121)[worker]), '-o', 'BatchMode=yes', '-o', PROXY,
                        'root@172.16.108.241:' + REMOTE + '/' + name, str(ROOT / name)], check=True, timeout=60)
    print(json.dumps({'worker': worker, 'state': 'accepted_not_started', 'paid_api_requests': 0}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--worker', type=int, required=True)
    parser.add_argument('--revision', type=int, default=1)
    args = parser.parse_args()
    main(args.worker, args.revision)
