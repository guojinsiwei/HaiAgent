"""Fresh campaign; verified old public assets and exact frozen source releases."""
import json
import os
from pathlib import Path
import shutil
import tarfile
from common import ROOT,sha,save

OLD=Path('/var/tmp/lizh639-longcli-v6-raw-paired10-20261001')
V6=Path('/var/tmp/lizh639-monitor-control-v6.1/sources')
V8=Path('/var/tmp/lizh639-lhtb-contrastive12-engineering-v2-20261002-r1/arms/common')

def code_hashes(root):
    return {p.relative_to(root).as_posix():sha(p) for p in sorted(root.rglob('*.py')) if '__pycache__' not in p.parts}

def main():
    if (ROOT/'arms').exists():raise RuntimeError('Never silently overwrite a prepared deployment')
    p=json.loads((ROOT/'protocol.json').read_text());old=json.loads((OLD/'protocol.json').read_text())
    if p['tasks']!=old['tasks'] or p['commit']!=old['commit']:raise RuntimeError('Original task inputs changed')
    v6_source=json.loads((V6.parent/'fixed-source-manifest.json').read_text())
    if code_hashes(V6)!=v6_source:raise RuntimeError('Frozen v6.1 source changed')
    v8_seal=json.loads((V8.parent.parent/'ready.json').read_text())
    if any(v8_seal['source_hashes'].get('arms/common/'+n)!=h for n,h in code_hashes(V8).items()):
        raise RuntimeError('Frozen v8 engineering-v2 source changed')
    if not (ROOT/'upstream').exists():
        shutil.copytree(OLD/'upstream',ROOT/'upstream',symlinks=True,ignore=shutil.ignore_patterns('__pycache__','.git'))
    manifest=json.loads((ROOT/'input-manifest.json').read_text())
    for name,digest in manifest['files'].items():
        # The new deployment helper differs; official task/tests/parser bytes may not.
        if name.startswith('upstream/') and sha(ROOT/name)!=digest:raise RuntimeError('Official source mismatch: '+name)
    (ROOT/'public').mkdir(exist_ok=True)
    for row in p['tasks']:
        source=ROOT/'upstream/tasks_long_cli'/row['task'];target=ROOT/'public'/row['task']
        target.mkdir(exist_ok=False)
        # Exactly the public Docker COPY inputs, never tests or reference answers.
        for line in (source/'Dockerfile').read_text().splitlines():
            if not line.startswith('COPY '):continue
            name=line.split()[1].removeprefix('./')
            if name in ('tests','run-tests.sh') or '/' in name:raise RuntimeError('Unexpected public COPY input')
            original=source/name
            if original.is_dir():shutil.copytree(original,target/name,symlinks=True)
            else:shutil.copy2(original,target/name)
        if not (target/'INSTRUCTION.md').is_file():raise RuntimeError('Public specification absent')
    (ROOT/'arms').mkdir()
    shutil.copytree(V6,ROOT/'arms/v6',ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copytree(V8,ROOT/'arms/v8',ignore=shutil.ignore_patterns('__pycache__'))
    save(ROOT/'arm-source-manifest.json',dict(v6=code_hashes(ROOT/'arms/v6'),v8=code_hashes(ROOT/'arms/v8'),
        source_origins={'v6':str(V6),'v8':str(V8)},no_algorithm_edits=True))
    # Reuse unchanged official image tags/IDs, never rebuild or regrade an old result.
    for family,info in p['base_images'].items():
        if sha(OLD/info['archive'])!=info['sha256']:raise RuntimeError('Official base archive changed')
    names=('common.py','environment.py','runner.py','worker.py','launch.py','net_transport.py','chroot_entry.py',
           'audit.py','cube_prepare.py','fixture_runner.py','shared_wire.py','admission.py','test_shared_wire.py',
           'historical-wire-failures.json','protocol.json','arm-source-manifest.json','prepare_cube.py')
    files=[ROOT/n for n in names]+[p for d in ('arms','public') for p in (ROOT/d).rglob('*')
        if p.is_file() and '__pycache__' not in p.parts]
    with tarfile.open(ROOT/'solver-inputs.tar.gz','x:gz',dereference=False) as archive:
        for path in files:archive.add(path,arcname=path.relative_to(ROOT).as_posix(),recursive=False)
    save(ROOT/'solver-input-manifest.json',dict(files={p.relative_to(ROOT).as_posix():sha(p) for p in files},
        archive_sha256=sha(ROOT/'solver-inputs.tar.gz'),hidden_grader_files_transferred=False,model_calls=0))
    print(json.dumps(dict(prepared=True,model_calls=0,archive_bytes=(ROOT/'solver-inputs.tar.gz').stat().st_size)))

if __name__=='__main__':main()
