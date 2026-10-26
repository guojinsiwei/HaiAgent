"""Host-only Docker filesystem snapshots for file-artifact tasks.

No Docker socket, controller key, host mirror or verifier files enter task sandboxes.
Snapshots contain the complete writable rootfs; detached task processes are refused,
not silently presented as restorable process state. Shared benchmark mounts are not
cloned. All Docker mutations are restricted to explicit per-trial owned IDs.
"""
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import uuid

from bestfgs.environment import (_tree_manifest, _manifest_fingerprint,
    _changed_manifest_paths, _validate_workspace_change, _verification_manifest)
from bestfgs.models import EnvironmentSnapshot, CommandResult, ExecutionOutcome
from haiagent.executor import Result

LABEL = 'org.bestfgs.lhtb.trial'
PYTHON = '/opt/lhtb-agent-tools/python/bin/python3.12'

class WorkBudgetExhausted(TimeoutError):
    """Normal wall budget stop; deliver a recorded candidate, not infra failure."""


class DockerState:
    def __init__(self, original, root, cpu, memory_mb, deadline):
        if not re.fullmatch(r'[a-f0-9]{12,64}', original):
            raise ValueError('Expected an exact Docker container ID')
        self.original, self.root = original, Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=False)
        self.owner = uuid.uuid4().hex
        self.cpu, self.memory_mb, self.deadline = cpu, memory_mb, deadline
        self.containers, self.images = set(), set()
        self.calls = 0
        info = json.loads(self.docker('inspect', original))[0]
        if any(m['Destination'] == '/app' or m['Destination'].startswith('/app/') for m in info['Mounts']):
            raise RuntimeError('Task workspace is a volume, not captured by rootfs snapshots')
        if info['Config'].get('Volumes'):
            raise RuntimeError('Image-declared volumes require a dedicated snapshot adapter')
        self.base_env = [v for v in info['Config'].get('Env', [])
                         if not any(s in v.split('=', 1)[0].upper() for s in ('KEY', 'TOKEN', 'SECRET', 'PASSWORD'))]
        self.log = self.root / 'commands.jsonl'
        self.snapshots = {}
        self.initial = self.capture(original, None)

    def docker(self, *args, timeout=180, input=None):
        result = subprocess.run(['docker', *map(str, args)], input=input,
                                capture_output=True, text=True, timeout=timeout)
        if result.returncode:
            # Never dump arbitrary task output into infrastructure exceptions.
            raise RuntimeError('Docker operation failed: ' + args[0])
        return result.stdout

    def reserve(self):
        if getattr(self, 'cancelled', None) is not None and self.cancelled.is_set():
            raise TimeoutError('Trial cancelled; refusing further container mutations')
        if min(shutil.disk_usage(self.root).free, shutil.disk_usage('/var/lib/docker').free) < 60 * 2**30:
            raise RuntimeError('Disk reserve under 60 GiB')

    def journal(self):
        p = self.root / 'owned.json'
        q = p.with_suffix('.tmp')
        q.write_text(json.dumps({'owner': self.owner, 'containers': sorted(self.containers),
                                'images': sorted(self.images)}))
        q.replace(p)

    def owned_container(self, container):
        if container not in self.containers:
            raise ValueError('Container not owned by this trial')
        info = json.loads(self.docker('inspect', container))[0]
        if (info['Config'].get('Labels') or {}).get(LABEL) != self.owner:
            raise ValueError('Docker ownership label mismatch')

    def branch(self, snapshot):
        self.reserve()
        if time.monotonic() >= self.deadline:
            raise WorkBudgetExhausted('Cumulative trial work budget exhausted')
        record = self.snapshots[snapshot.snapshot_id]
        args = ['run', '-d', '--label', LABEL + '=' + self.owner,
                '--network', 'container:' + self.original, '--cpus', str(self.cpu),
                '--memory', str(self.memory_mb) + 'm', '--memory-swap', str(self.memory_mb) + 'm',
                '--pids-limit', '512', '--entrypoint', PYTHON]
        for value in self.base_env:
            args.extend(['--env', value])
        args += [record['image'], '-c', 'import time; time.sleep(86400)']
        container = self.docker(*args).strip()
        self.containers.add(container)
        self.journal()
        return container

    def remove(self, container):
        self.owned_container(container)
        self.docker('rm', '-f', container)
        self.containers.remove(container)
        self.journal()

    def ensure_idle(self, container):
        # File-only checkpoint contract. Background daemons cannot be restored by
        # docker commit, so fail loudly instead of invalidating graph semantics.
        rows = self.docker('top', container, '-eo', 'pid').strip().splitlines()
        if len(rows) > 2:
            raise RuntimeError('Detached task process is incompatible with file-only snapshots')

    def mirror(self, container, target):
        target = Path(target)
        target.mkdir(parents=True, exist_ok=False)
        self.docker('cp', container + ':/app/.', target, timeout=600)
        # A mirror is never executed on the host. Reject links that could expose
        # host files to evidence inspection, instead of following container links.
        for base, dirs, files in os.walk(target, followlinks=False):
            for name in dirs + files:
                item = Path(base, name)
                if item.is_symlink():
                    resolved = item.resolve()
                    if not resolved.is_relative_to(target.resolve()):
                        raise RuntimeError('External symlink requires task-specific mirroring')

    def capture(self, container, parent):
        self.reserve()
        if container != self.original:
            self.owned_container(container)
            self.ensure_idle(container)
        sid = uuid.uuid4().hex
        image = self.docker('commit', '--change', 'LABEL ' + LABEL + '=' + self.owner,
                            container, 'lhtb-branch-' + self.owner + ':' + sid, timeout=600).strip()
        self.images.add(image)
        self.journal()
        location = self.root / sid
        self.mirror(container, location)
        manifest = _tree_manifest(location)
        # Track external filesystem writes as environment state too. The model
        # cannot make an apt install disappear merely by restoring /app.
        external = dict(self.snapshots[parent.snapshot_id]['external']) if parent else {}
        if parent:
            changes = self.docker('diff', container).splitlines()
            paths = []
            for line in changes:
                kind, path = line[0], line[2:]
                if path == '/app' or path.startswith(('/app/', '/opt/lhtb-agent-tools/')):
                    continue
                if kind == 'D':
                    for key in list(external):
                        if key == path or key.startswith(path + '/'):
                            external.pop(key)
                    external[path] = 'deleted'
                else:
                    paths.append(path)
            script = """import sys,json,pathlib,hashlib,stat,os
out={}
for name in json.load(sys.stdin):
 p=pathlib.Path(name)
 try:
  s=p.lstat()
  if stat.S_ISLNK(s.st_mode): v='link:'+os.readlink(p)
  elif stat.S_ISREG(s.st_mode):
   h=hashlib.sha256()
   with p.open('rb') as f:
    for b in iter(lambda:f.read(1048576),b''): h.update(b)
   v=str(s.st_mode)+':'+h.hexdigest()
  else: continue
  out[name]=v
 except FileNotFoundError: out[name]='deleted'
print(json.dumps(out))"""
            if paths:
                external.update(json.loads(self.docker('exec', '-i', container, PYTHON,
                    '-c', script, input=json.dumps(paths), timeout=600)))
        # Deduplicate immutable host mirrors; they are not mounted into any task.
        if parent:
            old = self.snapshots[parent.snapshot_id]
            for relative, value in manifest.items():
                new, previous = location / relative, Path(parent.location) / relative
                if value == old['manifest'].get(relative) and new.is_file() and not new.is_symlink():
                    new.unlink()
                    os.link(previous, new)
        root_manifest = self.snapshots[self.initial.snapshot_id]['manifest'] if parent else manifest
        fingerprint = hashlib.sha256(json.dumps([_manifest_fingerprint(manifest), external], sort_keys=True).encode()).hexdigest()
        snapshot = EnvironmentSnapshot(sid, str(location), fingerprint, 'Isolated full-rootfs file-only snapshot',
            {'changed_paths_from_root': _changed_manifest_paths(root_manifest, manifest),
             'changed_paths_from_parent': _changed_manifest_paths(self.snapshots[parent.snapshot_id]['manifest'], manifest) if parent else (),
             'container_filesystem_image': image, 'process_state': 'no_detached_processes'})
        self.snapshots[sid] = {'snapshot': snapshot, 'image': image, 'manifest': manifest, 'external': external}
        return snapshot

    def command(self, container, command, *, phase='action'):
        self.owned_container(container)
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise WorkBudgetExhausted('Cumulative trial work budget exhausted')
        value = dict(command)
        cwd = value.get('cwd', '.')
        if cwd.startswith(str(self.root)):
            # Public protocol uses /app; mirrored paths occur only in legacy prompts.
            parts = Path(cwd).relative_to(self.root).parts
            cwd = '/app/' + '/'.join(parts[1:])
        value['cwd'] = cwd
        raw = self.docker('exec', '-i', container, PYTHON,
                          '/opt/lhtb-agent-tools/container_command.py',
                          input=json.dumps({'command': value, 'remaining': remaining}),
                          timeout=min(remaining, 900) + 15)
        value_result = json.loads(raw)
        observation = value_result.pop('execution_observation', None)
        result = Result(**value_result)
        result.execution_observation = observation
        self.calls += 1
        if hasattr(self, 'audit'):
            self.audit.emit('tool_call', call_id=self.calls, phase=phase, command=value,
                            result=dict(result.payload(), execution_observation=observation), redundancy_label='unreviewed')
        with self.log.open('a') as stream:
            stream.write(json.dumps({'call_id': self.calls, 'phase': phase, 'command': value,
                                     'result': dict(result.payload(), execution_observation=observation), 'time': time.time()}) + '\n')
        self.ensure_idle(container)
        return result

    def deliver(self, snapshot):
        self.reserve()
        if snapshot.snapshot_id not in self.snapshots:
            raise ValueError('Unknown snapshot')
        # Only /app is a scored artifact location in the frozen task selection.
        # Full-rootfs images remain available for subsequent graph expansion.
        self.docker('exec', self.original, PYTHON, '-c',
            "import pathlib,shutil; p=pathlib.Path('/app'); assert p.is_dir() and not p.is_symlink(); "
            "[(x.unlink() if x.is_symlink() or x.is_file() else shutil.rmtree(x)) for x in p.iterdir()]")
        self.docker('cp', str(Path(snapshot.location)) + '/.', self.original + ':/app/', timeout=600)

class GraphEnvironment:
    def __init__(self, state, feedback):
        self.state, self.feedback = state, feedback

    def initial_snapshot(self):
        return self.state.initial

    def restore(self, snapshot):
        return self.state.snapshots[snapshot.snapshot_id]['snapshot']

    def submission_feedback(self, snapshot):
        self.state.deliver(snapshot)
        return self.feedback(snapshot)

    def invoke(self, container, command, phase):
        result = self.state.command(container, {'argv': list(command.argv), 'cwd': command.cwd,
            'stdin': command.stdin, 'timeout_seconds': command.timeout_seconds or 900,
            'purpose': command.description}, phase=phase)
        return CommandResult(command, result.exit_code if result.exit_code is not None else -1,
            result.stdout, result.stderr, result.duration_seconds, timed_out=result.timed_out,
            blocked=result.blocked, output_truncated=result.output_truncated)

    def execute(self, snapshot, action, max_commands):
        if hasattr(self.state, 'audit'):
            self.state.audit.emit('branch_selected', snapshot_id=snapshot.snapshot_id,
                fingerprint=snapshot.fingerprint, action=action.name,
                direction=action.semantic_direction_id)
        container = self.state.branch(snapshot)
        try:
            results = []
            for command in action.commands[:max_commands]:
                results.append(self.invoke(container, command, 'action'))
                if not results[-1].succeeded:
                    break
            child = self.state.capture(container, snapshot)
        finally:
            self.state.remove(container)
        validation = _validate_workspace_change(Path(snapshot.location), Path(child.location)) if child.fingerprint != snapshot.fingerprint else ()
        checks = ()
        remaining = max_commands - len(results)
        if results and all(r.succeeded for r in (*results, *validation)) and remaining > 0:
            checks = self.verify(child, action.verification_commands[:remaining])
        return ExecutionOutcome(snapshot, child, action, tuple(results),
            validation_results=validation, functional_validation_results=checks)

    def verify(self, snapshot, commands):
        if not commands:
            return ()
        container = self.state.branch(snapshot)
        try:
            results = []
            for command in commands:
                results.append(self.invoke(container, command, 'verification'))
                inspection = self.state.root / ('verify-' + uuid.uuid4().hex)
                self.state.mirror(container, inspection)
                changed = _changed_manifest_paths(_verification_manifest(Path(snapshot.location)), _verification_manifest(inspection))
                # Mirrors are private, never mounted/executed. Remove only this
                # validated newly created inspection child after checking it.
                if inspection.parent != self.state.root or inspection.is_symlink():
                    raise ValueError('Unsafe inspection directory')
                shutil.rmtree(inspection)
                if changed:
                    results[-1] = replace(results[-1], return_code=1,
                        stderr=results[-1].stderr + '\nVerification modified candidate files: ' + ', '.join(changed[:12]))
                if not results[-1].succeeded:
                    break
            return tuple(results)
        finally:
            self.state.remove(container)
