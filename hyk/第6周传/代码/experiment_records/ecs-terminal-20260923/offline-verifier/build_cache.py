"""Run on the experiment host to assemble immutable, task-specific offline bundles."""
from pathlib import Path
import hashlib
import json
import re
import tarfile

HOME = Path('/home/ecs-user')
CACHE = HOME / 'terminalbench-offline-recovery-20260924/cache'
TASKS = HOME / 'terminalbench-paired36-20260923-extended-v2/pinned-tasks'
BASE_WHEELS = HOME / 'terminalbench-offline-wheels-20260924'
EXTRA_WHEELS = HOME / 'terminalbench-offline-extra-wheels-20260924'
GROUPS = {
    'distribution-search': 'numpy230',
    'financial-document-processor': 'pandas',
    'install-windows-3-11': 'opencv-ocr',
    'make-mips-interpreter': 'numpy231-pillow',
    'model-extraction-relu-logits': 'numpy231',
    'path-tracing': 'numpy231-pillow',
    'pytorch-model-cli': 'torch271-vision',
    'regex-chess': 'chess',
    'sparql-university': 'rdflib',
    'torch-tensor-parallelism': 'torch270',
    'tune-mjcf': 'mujoco',
    'video-processing': 'toml-opencv-contrib',
}


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def bundle(group, files):
    path = CACHE / (group + '.tar.gz')
    inputs = {arc: sha(src) if src.is_file() else 'cpython-c0ccda275948c79996e46993c2c5476ff5cca606dee530f1dea712179131b348' for src, arc in files}
    stamp = path.with_suffix('.inputs.json')
    if not path.exists() or not stamp.exists() or json.loads(stamp.read_text()) != inputs:
        temp = path.with_suffix('.tmp')
        # Wheels already contain compressed data; avoid recompressing multi-GB groups.
        level = 0 if sum(src.stat().st_size for src, _ in files if src.is_file()) > 500_000_000 else 1
        with tarfile.open(temp, 'w:gz', compresslevel=level) as tar:
            for src, arc in files:
                def modes(info):
                    if info.name == 'transport/curl':
                        info.mode = 0o755
                    return info
                tar.add(src, arcname=arc, filter=modes)
        temp.replace(path)
        stamp.write_text(json.dumps(inputs, indent=2) + '\n')
    return {'file': path.name, 'sha256': sha(path), 'bytes': path.stat().st_size, 'inputs': inputs}


def build():
    CACHE.mkdir(exist_ok=True, parents=True)
    wheel_files = [(p, 'wheels/' + p.name) for p in sorted(BASE_WHEELS.glob('*.whl')) if not p.name.startswith('uv-')]
    base_files = wheel_files + [
        (CACHE / 'python/cpython-3.13.9-linux-x86_64-gnu', 'python/cpython-3.13.9-linux-x86_64-gnu'),
        (CACHE / 'bin/uv', 'bin/uv'), (CACHE / 'bin/uvx', 'bin/uvx'),
        (HOME / 'uv-install.sh', 'assets/uv-install.sh'),
        (HOME / 'uv-x86_64-unknown-linux-gnu.tar.gz', 'assets/uv-x86_64-unknown-linux-gnu.tar.gz'),
        (HOME / 'offline-shell.sh', 'offline-shell.sh'),
        (HOME / 'offline-curl.sh', 'transport/curl'),
    ]
    assert sha(HOME / 'uv-x86_64-unknown-linux-gnu.tar.gz') == '2cf10babba653310606f8b49876cfb679928669e7ddaa1fb41fb00ce73e64f66'
    assert sha(HOME / 'cpython-3.13.9-linux-x86_64.tar.gz') == 'c0ccda275948c79996e46993c2c5476ff5cca606dee530f1dea712179131b348'
    payloads = {'base': bundle('base', base_files)}
    groups = json.loads((HOME / 'extra-groups-files.json').read_text(encoding='utf-8-sig'))
    official = {r['filename']: r for r in json.loads((HOME/'extra-wheels-manifest.json').read_text(encoding='utf-8-sig'))}
    groups['numpy231'] = [p for p in groups['numpy231-pillow'] if p.startswith('numpy-')]
    for group, files in groups.items():
        if files and all((EXTRA_WHEELS / f).is_file() for f in files):
            for filename in files:
                item = official[filename]
                if not item['verified'] or sha(EXTRA_WHEELS/filename) != item['official_sha256']:
                    raise RuntimeError('Uploaded dependency failed official SHA256: ' + filename)
            payloads[group] = bundle(group, [(EXTRA_WHEELS / f, 'wheels/' + f) for f in files])
    tasks = {}
    for path in sorted(TASKS.glob('*/tests/test.sh')):
        name = path.parent.parent.name
        script = path.read_text()
        requirements = re.findall(r'-w\s+(\S+)', script) or ['pytest==8.4.1', 'pytest-json-ctrf==0.3.5']
        tasks[name] = {'group': GROUPS.get(name, 'base'), 'requirements': requirements,
                       'test_script_sha256': sha(path), 'native_pip': name == 'build-cython-ext',
                       'indexes': [l.strip().rstrip('\\').strip() for l in script.splitlines() if '--index' in l]}
    manifest = {'version': 1, 'scope': 'Python/uv/pytest dependencies for verifier phase only; apt and task runtime network unchanged',
                'python': '3.13.9', 'uv': '0.9.5', 'tasks': tasks, 'payloads': payloads,
                'complete': all(t['group'] in payloads for t in tasks.values())}
    (CACHE / 'offline-cache-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({'complete': manifest['complete'], 'payloads': list(payloads), 'tasks': len(tasks),
                      'missing_groups': sorted({t['group'] for t in tasks.values()} - payloads.keys())}))


if __name__ == '__main__':
    build()
