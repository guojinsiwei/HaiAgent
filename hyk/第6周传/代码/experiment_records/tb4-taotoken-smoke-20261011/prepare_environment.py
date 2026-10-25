"""Change only the download registry, retaining the official immutable image."""
from pathlib import Path
import hashlib
import json
import shutil

root = Path(__file__).resolve().parent
original = root / 'terminal-bench/tasks/wal-recovery-ordering'
target = root / 'task-transport/wal-recovery-ordering'
if target.exists():
    raise SystemExit('Transport task already exists; refusing overwrite')
shutil.copytree(original, target)
changes = []
for relative in ('environment/Dockerfile', 'tests/Dockerfile'):
    path = target / relative
    data = path.read_text()
    assert 'FROM python:3.13-slim-bookworm@sha256:' in data, relative
    new = data.replace('FROM python:3.13-slim-bookworm@sha256:',
                       'FROM docker.m.daocloud.io/library/python:3.13-slim-bookworm@sha256:')
    path.write_text(new)
    changes.append({'file': relative, 'before_sha256': hashlib.sha256(data.encode()).hexdigest(),
                    'after_sha256': hashlib.sha256(new.encode()).hexdigest(),
                    'change': 'registry transport only; original immutable image digest retained'})
(root / 'transport-changes.json').write_text(json.dumps(changes, indent=2))
