"""Owned run records and safe file-artifact transport."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import tarfile
import time

ROOT = Path(__file__).resolve().parent
PYTHON = '/mnt/lizh639/envs/swe-eval/bin/python'

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1048576), b''):
            h.update(chunk)
    return h.hexdigest()

def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name+'.tmp')
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')
    os.replace(tmp, path)

def entries(root, source_only=False):
    root = Path(root)
    total = 0
    count = 0
    for parent, dirs, files in os.walk(root, followlinks=False):
        if source_only:
            dirs[:] = [d for d in dirs if d not in {'.git', '__pycache__', '.pytest_cache',
                '.tbench-testing', '.venv', 'venv', 'test_output', 'CMakeFiles',
                'build','build_hw2','build_hw3','build_hw5','build_hw6'}]
        for name in sorted(dirs+files):
            path = Path(parent)/name
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode):
                target = os.readlink(path)
                if PurePosixPath(target).is_absolute() or not path.resolve().is_relative_to(root.resolve()):
                    raise RuntimeError('Refusing external artifact link')
            elif not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
                raise RuntimeError('Refusing special artifact file')
            if source_only and path.suffix in {'.o', '.a', '.so', '.pyc'}:
                continue
            total += info.st_size if stat.S_ISREG(info.st_mode) else 0
            count += 1
            if count > 50000 or total > 2*2**30:
                raise RuntimeError('Artifact bound exceeded; preserve for inspection')
            yield path

def export_tree(root, archive, source_only=False):
    rows = list(entries(root, source_only))
    with tarfile.open(archive, 'x:gz', dereference=False) as stream:
        for path in rows:
            stream.add(path, arcname=path.relative_to(root).as_posix(), recursive=False)
    return dict(path=str(archive), sha256=sha(archive), entries=len(rows), source_only=source_only)

def import_tree(archive, target):
    target = Path(target)
    target.mkdir(parents=True, exist_ok=False)
    with tarfile.open(archive, 'r:gz') as stream:
        members = stream.getmembers()
        total = 0
        for member in members:
            name = PurePosixPath(member.name)
            if name.is_absolute() or '..' in name.parts or not (member.isfile() or member.isdir() or member.issym()):
                raise RuntimeError('Unsafe archive member')
            total += member.size
            if total > 2*2**30 or len(members) > 50000:
                raise RuntimeError('Oversized artifact')
            if member.issym():
                link = PurePosixPath(member.linkname)
                if link.is_absolute() or not (target/member.name).parent.joinpath(member.linkname).resolve().is_relative_to(target.resolve()):
                    raise RuntimeError('Unsafe archive link')
        # Links are last, so no member can extract through an archive-made link.
        links = {m.name.rstrip('/') for m in members if m.issym()}
        if any(any(parent.as_posix() in links for parent in PurePosixPath(m.name).parents) for m in members):
            raise RuntimeError('Archive parent is a link')
        stream.extractall(target, members=sorted(members,key=lambda m:m.issym()), filter='data')
        # data_filter strips writable bits; checkpoints must retain ordinary modes.
        # Special bits are intentionally never restored.
        for member in members:
            if not member.issym(): os.chmod(target/member.name,member.mode & 0o777)

def validate():
    ready = json.loads((ROOT/'ready.json').read_text())
    if not ready.get('ready'): raise RuntimeError('Acceptance not complete; no paid run permitted')
    for name, expected in ready['hashes'].items():
        if sha(ROOT/name) != expected:
            raise RuntimeError('Sealed input changed: '+name)
    return json.loads((ROOT/'protocol.json').read_text())

def assignments(protocol, worker):
    rows = []
    for row in protocol['tasks']:
        methods=protocol['methods']
        offset=row['index']%len(methods)
        for j,method in enumerate(methods[offset:]+methods[:offset]):
            if (row['index']*len(methods)+j)%2==worker:
                rows.append(dict(row,method=method,job=method+'--'+row['task'],worker=worker))
    return rows
