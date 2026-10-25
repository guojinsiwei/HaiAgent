import json
import subprocess
import sys


def main():
    options = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15']
    result = subprocess.run(options + ['cubestudio_container', '/mnt/lizh639/envs/bestfgs/bin/tmux show-environment -g DEEPSEEK_API_KEY'], capture_output=True, text=True, timeout=30, check=True)
    if not result.stdout.startswith('DEEPSEEK_API_KEY='):
        raise RuntimeError('Credential missing')
    key = result.stdout.strip().split('=', 1)[1]
    for index, host in enumerate(('cubestudio_container', 'cubestudio_container2')):
        result = subprocess.run(options + [host, '/mnt/lizh639/envs/bestfgs/bin/python /mnt/lizh639/notebook-tools/install_paired_guard.py'],
                                input=json.dumps({'key': key, 'index': index}), capture_output=True, text=True, timeout=45)
        print(result.stdout, flush=True)
        if result.returncode:
            raise RuntimeError('Setup failed')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('SETUP_FAILED', type(exc).__name__)
        sys.exit(2)
