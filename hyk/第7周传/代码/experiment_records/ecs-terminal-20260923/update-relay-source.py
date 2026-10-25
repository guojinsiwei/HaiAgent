"""Rotate only the already-authorized relay source; preserve all login keys."""
from pathlib import Path
import os

path = Path('/home/ecs-user/.ssh/authorized_keys')
marker = 'terminalbench-download-relay-20260923'
old = 'from="154.213.1.67",'
new = 'from="58.249.112.44",'
lines = path.read_text().splitlines(keepends=True)
matches = [i for i, line in enumerate(lines) if line.rstrip().endswith(marker)]
assert len(matches) == 1, 'Expected one restricted relay authorization'
i = matches[0]
assert lines[i].startswith((old, new)), 'Unexpected authorization; refusing edit'
lines[i] = lines[i].replace(old, new, 1)
temp = path.with_name('authorized_keys.relay-update')
fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, 'w') as stream:
    stream.writelines(lines)
os.replace(temp, path)
print('Relay source rotated; all other authorization restrictions preserved')
