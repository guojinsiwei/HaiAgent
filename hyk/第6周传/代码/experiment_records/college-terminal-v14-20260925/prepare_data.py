"""Prepare the original fixed sample; no model or official verifier execution."""
import fcntl
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time

ROOT = Path.home() / 'terminalbench-v14-setup'
MIRROR_PREFIX = 'dockerproxy.net/'

def save(value):
    p = ROOT / 'preparation.json'
    t = p.with_suffix('.tmp')
    t.write_text(json.dumps(value, indent=2))
    t.replace(p)

def main():
    lock = (ROOT / 'prepare.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    old = json.loads((ROOT / 'original-protocol.json').read_text())['protocol']
    selection = json.loads((ROOT / 'task-selection.json').read_text())
    if [x['id'] for x in old['tasks']] != [x['id'] for x in selection['tasks']]:
        raise RuntimeError('Historical task lists disagree')
    state = {'phase': 'dataset', 'total': 36, 'images_ready': [], 'started': time.time()}
    save(state)
    try:
        dataset = ROOT / 'datasets' / 'terminal-bench-2'
        if not dataset.exists():
            subprocess.run([str(ROOT / 'runtime/bin/harbor'), 'datasets', 'download',
                            'terminal-bench/terminal-bench-2', '--output-dir', str(ROOT / 'datasets')], check=True)
        for task in old['tasks']:
            name = task['id'].split('/')[-1]
            for rel, expected in task['source_files'].items():
                p = dataset / name / rel
                if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest() != expected:
                    raise RuntimeError(f'Historical task hash mismatch: {name}/{rel}')
        state['phase'] = 'images'
        for task in old['tasks']:
            if shutil.disk_usage(ROOT).free < 60 * 1024**3 or shutil.disk_usage('/').free < 60 * 1024**3:
                raise RuntimeError('Disk reserve below 60 GiB; preparation stopped')
            state.update(current=task['id'], updated=time.time())
            save(state)
            source_ref = MIRROR_PREFIX + task['pinned_image']
            for attempt in range(3):
                result = subprocess.run(['docker', 'pull', source_ref], timeout=3600)
                if result.returncode == 0:
                    break
                if attempt == 2:
                    raise RuntimeError('Official image download failed after 3 attempts: ' + task['id'])
                time.sleep(10 * (attempt + 1))
            details = json.loads(subprocess.check_output(['docker', 'image', 'inspect', source_ref]))[0]
            if source_ref not in details.get('RepoDigests', []):
                raise RuntimeError('Image identity mismatch')
            state['images_ready'].append(task['id'])
            state.setdefault('transport_refs', {})[task['id']] = source_ref
            save(state)
        state.update(phase='data_ready', current=None, finished=time.time())
        save(state)
    except Exception as error:
        state.update(phase='needs_attention', error=str(error), updated=time.time())
        save(state)
        raise

if __name__ == '__main__':
    main()
