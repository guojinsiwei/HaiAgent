"""Credentials stay in process memory and encrypted SSH stdin only."""
import json
from pathlib import Path
import subprocess
import sys

HOSTS = ['cubestudio_container', 'cubestudio_container2']
PYTHON = '/mnt/lizh639/envs/bestfgs/bin/python'
HELPER = '/mnt/lizh639/notebook-tools/paired_remote_launch_v5.py'


def ssh(host, command, payload=None, timeout=100):
    result = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15', host, command],
                            input=payload, capture_output=True, text=True, encoding='utf-8', timeout=timeout)
    if result.returncode:
        try:
            safe = json.loads(result.stdout)
            print(json.dumps({k: safe[k] for k in ('error', 'status', 'stage') if k in safe}), flush=True)
        except (ValueError, TypeError):
            print('SSH_EXIT', host, result.returncode, flush=True)
        raise RuntimeError('Remote validation/launch failed on ' + host + '; no secret output displayed')
    return result.stdout


def main():
    secret = ssh(HOSTS[0], '/mnt/lizh639/envs/bestfgs/bin/tmux show-environment -g DEEPSEEK_API_KEY')
    if not secret.startswith('DEEPSEEK_API_KEY='):
        raise RuntimeError('Missing credential in first notebook tmux')
    key = secret.strip().split('=', 1)[1]
    checked = []
    for index, host in enumerate(HOSTS):
        response = json.loads(ssh(host, PYTHON + ' ' + HELPER, json.dumps({'index': index, 'action': 'preflight', 'key': key})))
        print(json.dumps({k: v for k, v in response.items() if k != 'assigned_ids'}), flush=True)
        checked.append(response)
    if checked[0]['protocol_sha256'] != checked[1]['protocol_sha256']:
        raise RuntimeError('Notebook protocols differ')
    shards = [set(row['assigned_ids']) for row in checked]
    if shards[0] & shards[1] or len(shards[0] | shards[1]) != 100:
        raise RuntimeError('Task overlap or missing task')
    print('PREFLIGHT_OK: same protocol; disjoint 50+50; both API authentications passed', flush=True)
    if '--start' not in sys.argv:
        return
    for index, host in enumerate(HOSTS):
        payload = {'index': index, 'action': 'start', 'key': key, 'protocol_sha256': checked[index]['protocol_sha256']}
        response = json.loads(ssh(host, PYTHON + ' ' + HELPER, json.dumps(payload)))
        print(json.dumps(response), flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(type(error).__name__ + ': launch stopped; inspect worker status before any retry', file=sys.stderr)
        sys.exit(2)
