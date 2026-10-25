from pathlib import Path
import hashlib
import json

root=Path(__file__).resolve().parent
path=root/'task-transport/wal-recovery-ordering/tests/Dockerfile'
text=path.read_text()
assert text.count('RUN pip install ') == 1
text=text.replace('RUN pip install ', 'RUN HTTPS_PROXY=http://10.123.0.1:28476 pip install ')
path.write_text(text)
manifest=root/'transport-changes.json'
entries=json.loads(manifest.read_text())
entries.append({'file':'tests/Dockerfile', 'change':'Restricted HTTPS CONNECT proxy for build-time PyPI; package pins unchanged',
    'after_sha256':hashlib.sha256(text.encode()).hexdigest()})
manifest.write_text(json.dumps(entries,indent=2))
