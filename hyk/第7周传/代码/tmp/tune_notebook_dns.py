"""Scoped resolver repair: retain cluster nameserver/search, change ndots only."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

host = os.uname().nodename
if host not in ('lizh639-aa91', 'lizh639-8e64'):
    raise SystemExit('Unexpected host')
path = Path('/etc/resolv.conf')
old = path.read_bytes()
text = old.decode()
if 'nameserver 10.43.0.10' not in text or not re.search(r'\bndots:5\b', text):
    raise SystemExit('Resolver differs from inspected configuration; stopped')
new = re.sub(r'\bndots:5\b', 'ndots:1', text).encode()
stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
directory = Path('/mnt/lizh639/notebook-checks') / f'dns-{host}-{stamp}'
directory.mkdir(parents=True, exist_ok=False)
(directory / 'resolv.conf.before').write_bytes(old)
# resolv.conf can be bind-mounted; preserve the inode and file permissions.
with path.open('wb') as stream:
    stream.write(new)
    stream.flush()
    os.fsync(stream.fileno())
rows = []
for _ in range(3):
    try:
        result = subprocess.run([sys.executable, '-c', "import socket; assert socket.getaddrinfo('api.deepseek.com',443)"],
                                capture_output=True, timeout=18)
        rows.append(result.returncode == 0)
    except subprocess.TimeoutExpired:
        rows.append(False)
if not any(rows):
    path.write_bytes(old)
    outcome = 'rolled_back_all_probes_failed'
else:
    outcome = 'applied'
audit = {'host': host, 'at': stamp, 'change': 'ndots:5 -> ndots:1; nameserver/search unchanged',
         'before_sha256': hashlib.sha256(old).hexdigest(), 'after_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
         'probe_success': rows, 'outcome': outcome, 'backup': str(directory / 'resolv.conf.before'),
         'scope': 'notebook OS DNS resolution only; no model/algorithm/budget/seed changes'}
(directory / 'audit.json').write_text(json.dumps(audit, indent=2) + '\n')
print(json.dumps(audit))
if outcome != 'applied':
    sys.exit(2)
