"""Adapter for the existing host-only LHTB DockerState infrastructure.

The owning harness injects DockerState; no socket, API key or host paths enter the
task. Unlike GraphEnvironment, ordinary commands reuse one live container.
Capture/commit occurs only at checkpoint or delivery. No live deployment here.
"""
import json
import time
import uuid
from .models import CommandSpec, CommandResult
from .lean_progress import normalize_workspace_path


# File state for repeat observations, not an assertion about processes/network.
FINGERPRINT_SCRIPT = '''import os,hashlib,json,stat
rows=[]
for base,dirs,files in os.walk('/app',followlinks=False):
 dirs[:]=sorted(d for d in dirs if d not in {'.git','__pycache__'})
 for name in sorted(files+[d for d in dirs if os.path.islink(os.path.join(base,d))]):
  p=os.path.join(base,name); s=os.lstat(p)
  if stat.S_ISLNK(s.st_mode): value='link:'+os.readlink(p)
  elif stat.S_ISREG(s.st_mode):
   h=hashlib.sha256()
   with open(p,'rb') as f:
    for b in iter(lambda:f.read(1048576),b''): h.update(b)
   value=h.hexdigest()
  else: continue
  rows.append([os.path.relpath(p,'/app'),s.st_mode & 511,value])
print(hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest())
'''

DEPENDENCY_SCRIPT = '''import sys,os,hashlib,json,stat
def file_value(p):
 s=os.lstat(p)
 if stat.S_ISLNK(s.st_mode): return 'link:'+os.readlink(p)
 if stat.S_ISREG(s.st_mode):
  h=hashlib.sha256()
  with open(p,'rb') as f:
   for b in iter(lambda:f.read(1048576),b''): h.update(b)
  return 'file:'+str(s.st_size)+':'+h.hexdigest()
 if stat.S_ISDIR(s.st_mode):
  rows=[]
  for base,dirs,files in os.walk(p,followlinks=False):
   dirs[:]=sorted(dirs)
   for name in sorted(files+[d for d in dirs if os.path.islink(os.path.join(base,d))]):
    q=os.path.join(base,name)
    try: rows.append([os.path.relpath(q,p),file_value(q)])
    except FileNotFoundError: rows.append([os.path.relpath(q,p),'missing'])
  return 'dir:'+hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest()
 return 'other'
out={}
for name in json.load(sys.stdin):
 p=os.path.join('/app',*name.split('/'))
 try: out[name]=file_value(p)
 except FileNotFoundError: out[name]='missing'
print(json.dumps(out,sort_keys=True))
'''


class ContinuousDockerEnvironment:
    def __init__(self, state, python='/opt/lhtb-agent-tools/python/bin/python3.12'):
        self.state, self.python = state, python
        self.current = state.initial
        self.container = state.branch(self.current)
        self.records = {}
        self.dirty = False
        self.scope_revision = 0
        self._scope_cache = None

    def scope(self):
        self.state.owned_container(self.container)
        if self._scope_cache is None:
            self._scope_cache = self.state.docker('exec', self.container, self.python, '-c', FINGERPRINT_SCRIPT,
                timeout=max(1, min(60, self.state.deadline-time.monotonic()))).strip()
        return self._scope_cache

    def dependency_state(self, paths):
        self.state.owned_container(self.container)
        names = [normalize_workspace_path(path) for path in paths]
        if not names:
            return {}
        raw = self.state.docker('exec', '-i', self.container, self.python, '-c', DEPENDENCY_SCRIPT,
            input=json.dumps(names), timeout=max(1, min(120, self.state.deadline-time.monotonic())))
        value = json.loads(raw)
        if set(value) != set(names) or not all(isinstance(item, str) for item in value.values()):
            raise RuntimeError('invalid dependency inspection result')
        return value

    def execute(self, action, deadline):
        if time.monotonic() >= deadline:
            raise TimeoutError('work budget exhausted')
        command = CommandSpec(tuple(action['argv']), action.get('purpose',''), action.get('cwd','.'),
                              action.get('timeout_seconds',60), action.get('stdin'))
        self.dirty = True  # External writes may occur without changing /app.
        result = self.state.command(self.container, action)
        self._scope_cache = None
        return CommandResult(command, result.exit_code if result.exit_code is not None else -1,
            result.stdout, result.stderr, result.duration_seconds, timed_out=result.timed_out,
            blocked=result.blocked, output_truncated=result.output_truncated)

    def checkpoint(self, label):
        if self.dirty:
            self.current = self.state.capture(self.container, self.current)
            self.dirty = False
        record = dict(id=uuid.uuid4().hex, snapshot_id=self.current.snapshot_id, path=self.current.location,
                      fingerprint=self.current.fingerprint, label=label,
                      observable_scope=self.scope(),
                      restoration='container_filesystem_only')
        self.records[record['id']] = record
        return dict(record)

    def restore(self, record):
        if self.records.get(record['id']) != record:
            raise ValueError('unowned checkpoint')
        snapshot = self.state.snapshots[record['snapshot_id']]['snapshot']
        if snapshot.fingerprint != record['fingerprint']:
            raise RuntimeError('checkpoint identity mismatch')
        # Start the replacement first; keep current work if creation fails.
        replacement = self.state.branch(snapshot)
        self.state.remove(self.container)
        self.container, self.current, self.dirty = replacement, snapshot, False
        self.scope_revision += 1
        self._scope_cache = record['observable_scope']

    def delivery(self):
        self.checkpoint('delivery')
        self.state.deliver(self.current)
        return dict(path=self.current.location, fingerprint=self.current.fingerprint,
                    snapshot_id=self.current.snapshot_id, restoration='container_filesystem_only')

    def close(self):
        self.state.remove(self.container)
