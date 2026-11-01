"""Vendor pinned verifier wheels; scoring code and versions stay unchanged."""
import hashlib
import json
from pathlib import Path
import shutil

root=Path(__file__).resolve().parent
target=root/'task-transport/wal-recovery-ordering/tests'
shutil.copytree(root/'wheelhouse',target/'wheels')
dockerfile=target/'Dockerfile'
text=dockerfile.read_text()
before='RUN HTTPS_PROXY=http://10.123.0.1:28476 pip install --no-cache-dir '
assert text.count(before)==1
text=text.replace(before,'COPY wheels/ /opt/verifier-wheels/\nRUN pip install --no-cache-dir --no-index --find-links /opt/verifier-wheels ')
dockerfile.write_text(text)
manifest=root/'transport-changes.json'
entries=json.loads(manifest.read_text())
entries.append({'file':'tests/Dockerfile','change':'Offline wheel delivery; test scripts and three package pins unchanged',
    'wheels':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((target/'wheels').glob('*.whl'))},
    'after_sha256':hashlib.sha256(text.encode()).hexdigest()})
manifest.write_text(json.dumps(entries,indent=2))
