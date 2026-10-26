"""Trusted rootfs/public source preparation, no model calls and no hidden tests."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from runner import HERE, run_one

BASE = Path('/mnt/lizh639/longcli-portability-20260927')
TASKS = ['cs61_fa24_scheme', 'cs61_fa24_ants', 'cs61_fa24_cats']

def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(1024*1024), b''):
            h.update(b)
    return h.hexdigest()

def main():
    assert not (HERE / 'health.json').exists(), 'Never prepare a launched experiment'
    isolation = json.loads((BASE/'isolation-result.json').read_text())
    assert all(isolation.values())
    assert json.loads((HERE/'acceptance.json').read_text())['passed']
    upstream = BASE/'public-upstream'
    commit = subprocess.check_output(['git', '-C', str(upstream), 'rev-parse', 'HEAD'], text=True).strip()
    assert commit == '2015f37b5c458f2562354de6b415e9182c91af64'
    manifest = {
        'version': 'longcli-raw3-diagnostic-v1', 'tasks': TASKS, 'commit': commit,
        'selection': 'Three Python/Scheme file-artifact tasks with same base image; no outcome-based selection.',
        'model': 'deepseek-flash', 'endpoint': 'https://api.deepseek.com', 'thinking': 'disabled',
        'image_id': 'sha256:5568ac38fe7ad7bf91717543babf5852819736facbb067f3889788c45b8f0fea',
        'rootfs_sha256': sha(BASE/'raw3-rootfs.tar'), 'method': 'raw', 'concurrency': 1,
        'budgets': {'max_turns': 800, 'max_tools': 600, 'wall_seconds': 7200,
                    'command_seconds': 300, 'request_seconds': 180, 'api_attempts': 2,
                    'max_tokens': 4096, 'prompt_bytes': 48000, 'output_bytes': 16000, 'temperature': 0},
        'grading': 'Unmodified pinned official tests on a separate Docker grading host; no online verifier feedback.',
        'isolation': isolation, 'task_files': {},
    }
    for task_id in TASKS:
        root = HERE/'roots'/task_id
        root.mkdir(parents=True, exist_ok=False)
        subprocess.run(['tar', '-xf', str(BASE/'raw3-rootfs.tar'), '-C', str(root), '--no-same-owner'], check=True)
        source = upstream/'tasks_long_cli'/task_id
        for name in [task_id, 'attachments', 'INSTRUCTION.md']:
            p = source/name
            if p.is_dir():
                shutil.copytree(p, root/'app'/name, symlinks=True)
            elif p.is_file():
                shutil.copy2(p, root/'app'/name)
        assert (root/'app'/task_id).is_dir()
        assert not (root/'tests').exists()
        # Only task data and temporary files are owned by the sandbox UID.
        for base in [root/'app', root/'tmp']:
            for parent, dirs, files in os.walk(base, followlinks=False):
                os.chown(parent, 65534, 65534, follow_symlinks=False)
                for name in dirs + files:
                    os.chown(Path(parent)/name, 65534, 65534, follow_symlinks=False)
        manifest['task_files'][task_id] = {str(p.relative_to(root/'app')): sha(p)
            for p in (root/'app').rglob('*') if p.is_file() and not p.is_symlink()}
        print(json.dumps({'prepared': task_id}), flush=True)
    (HERE/'protocol.json').write_text(json.dumps(manifest, indent=2))
    for task_id in TASKS:
        result = run_one(task_id, '', fixture=True)
        assert result['submitted'] and result['tool_calls'] == 1
        events = [json.loads(x) for x in (HERE/'fixtures'/task_id/'events.jsonl').read_text().splitlines()]
        assert any('fixture-ok' in json.dumps(e) for e in events)
    hashes = {str(p.relative_to(HERE)): sha(p) for p in HERE.rglob('*.py')
              if p.is_relative_to(HERE/'runtime') or p.parent == HERE}
    hashes['protocol.json'] = sha(HERE/'protocol.json')
    hashes['acceptance.json'] = sha(HERE/'acceptance.json')
    (HERE/'ready.json').write_text(json.dumps({'ready': True, 'hashes': hashes, 'model_calls': 0}, indent=2))
    print(json.dumps({'ready': True, 'model_calls': 0}), flush=True)

if __name__ == '__main__':
    main()
