"""Model-free local result return; generation and grading continue on the server."""
import json
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parent
REMOTE = '/var/tmp/lizh639-longcli-dsh20-repair2-20261005'
PYTHON = '/mnt/sdb/home/lizh639/terminalbench-v14-setup/runtime/bin/python'
SSH = ['ssh', '-i', 'C:/Users/54177/.ssh/cubestudio_notebook', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15', 'lizh639@172.16.108.236']


def main():
    while True:
        try:
            p = subprocess.run(SSH + ['cat ' + REMOTE + '/health.json'], capture_output=True, text=True, timeout=45)
            if p.returncode:
                raise RuntimeError('SSH status read failed')
            health = json.loads(p.stdout)
            (ROOT / 'remote-health.json').write_text(json.dumps(health, indent=2), encoding='utf-8')
            if health['state'] in ('complete', 'needs_attention'):
                result = subprocess.run(SSH + [PYTHON + ' -B ' + REMOTE + '/return_artifacts.py'],
                                        capture_output=True, text=True, timeout=120, check=True)
                info = json.loads(result.stdout)
                assert info['archive'].startswith(REMOTE + '/results-') and info['archive'].endswith('.tar.gz')
                destination = ROOT / Path(info['archive']).name
                subprocess.run(['scp', '-i', 'C:/Users/54177/.ssh/cubestudio_notebook', '-o', 'BatchMode=yes',
                                'lizh639@172.16.108.236:' + info['archive'], str(destination)], check=True, timeout=300)
                (ROOT / 'result-return.json').write_text(json.dumps({**info, 'local_archive': str(destination)}, indent=2), encoding='utf-8')
                print(json.dumps(info), flush=True)
                return
        except Exception as error:
            # Only retry read-only status/download; never launch, replay or regrade a task.
            print(json.dumps({'state': 'return_wait', 'error_type': type(error).__name__}), flush=True)
        time.sleep(60)


if __name__ == '__main__':
    main()
