"""Same isolated command executor for v6 and RAW; no Docker on solvers."""
from dataclasses import asdict
import json
import os
from pathlib import Path
import posixpath
import shutil
import sys
import time
import uuid

from common import ROOT, PYTHON, export_tree, import_tree, sha
ARM=ROOT/'arms'/('v8' if os.environ.get('LONGCLI_METHOD')=='orthogonal-v8' else 'v6')
sys.path[:0] = [str(ARM/'bestfgs-project/src'),str(ARM/'hai-project/src')]
from haiagent.executor import LocalExecutor, Result
from haiagent.protocol import Config, Task
from bestfgs.models import CommandSpec, CommandResult
from bestfgs.lean_docker import FINGERPRINT_SCRIPT, DEPENDENCY_SCRIPT
from bestfgs.lean_progress import normalize_workspace_path
from bestfgs.shell_probe import prepare_trace, finish_trace

class SandboxExecutor(LocalExecutor):
    def __init__(self, root, seconds=300):
        self.image_root = Path(root)
        super().__init__(Task('executor','Infrastructure',self.image_root/'app',delivery='terminal'),
                         Config(method='raw',command_seconds=seconds,output_bytes=24000))

    def execute(self, command, deadline):
        command = dict(command)
        cwd = command.get('cwd','.')
        if cwd == str(self.root) or cwd.startswith(str(self.root)+'/'):
            cwd = '/app'+cwd[len(str(self.root)):]
        cwd = posixpath.normpath(posixpath.join('/app',cwd))
        if cwd != '/app' and not cwd.startswith('/app/'):
            return Result(126, stderr='cwd must be inside /app', blocked=True)
        argv = ['setpriv','--reuid','65534','--regid','65534','--clear-groups',
                'unshare','--user','--map-root-user','--pid','--net','--fork','--kill-child=KILL',
                PYTHON,str(ROOT/'chroot_entry.py'),str(self.image_root),
                json.dumps(dict(cwd=cwd,argv=command['argv']))]
        command.update(argv=argv,cwd='.',timeout_seconds=command.get('timeout_seconds',60))
        result = super().execute(command, deadline)
        return result

    def observation_cwd(self, command):
        cwd = command.get('cwd','.')
        if cwd.startswith('/app'):
            cwd = cwd[4:].lstrip('/')
        return str(self.root/cwd)

class NativeEnvironment:
    def __init__(self, root, output):
        self.image_root = Path(root)
        self.workspace = self.image_root/'app'
        self.root = Path(output)
        self.root.mkdir(parents=True,exist_ok=False)
        self.executor = SandboxExecutor(root)
        self.records = {}
        self._scope_cache = None
        self.outcome_reliability = False

    def probe(self, script, stdin=None):
        result = self.executor.execute(dict(argv=['python3','-c',script],cwd='.',
            stdin=stdin,timeout_seconds=90),time.monotonic()+90)
        if result.exit_code or result.output_truncated:
            raise RuntimeError('Isolated observation failed: '+result.stderr[-200:])
        return result.stdout.strip()

    def scope(self):
        if self._scope_cache is None:
            self._scope_cache = self.probe(FINGERPRINT_SCRIPT)
        return self._scope_cache

    def dependency_state(self, paths):
        names = [normalize_workspace_path(p) for p in paths]
        return json.loads(self.probe(DEPENDENCY_SCRIPT,json.dumps(names))) if names else {}

    def observe_state(self, paths):
        return self.scope(),self.dependency_state(paths)

    def execute(self, action, deadline):
        original = dict(action)
        handle = None
        if self.outcome_reliability:
            action, handle = prepare_trace(action)
        if handle is not None:
            _, path, _, _ = handle
            isolated = '/tmp/fgs-trace-'+uuid.uuid4().hex
            action = dict(action,argv=[part.replace(str(path),isolated) for part in action['argv']])
        try:
            result = self.executor.execute(action, deadline)
            if handle is not None:
                content = self.probe("from pathlib import Path; p=Path("+repr(isolated)+
                    "); print(p.read_text()[:65536] if p.is_file() else '',end='')")
                path.write_text(content)
        finally:
            observation = finish_trace(handle) if self.outcome_reliability else None
            self._scope_cache = None
        spec = CommandSpec(tuple(original['argv']),original.get('purpose',''),original.get('cwd','.'),
                           original.get('timeout_seconds',60),original.get('stdin'))
        return CommandResult(spec,result.exit_code if result.exit_code is not None else -1,
            result.stdout,result.stderr,result.duration_seconds,timed_out=result.timed_out,
            blocked=result.blocked,output_truncated=result.output_truncated,
            execution_observation=observation)

    def checkpoint(self, label):
        ident = uuid.uuid4().hex
        archive = self.root/(ident+'.tar.gz')
        before = self.scope()
        record = dict(id=ident,label=label,fingerprint=before,path=str(archive),
                      archive_sha256=export_tree(self.workspace,archive)['sha256'],
                      restoration='workspace_files_only')
        if self.scope()!=before:
            raise RuntimeError('Checkpoint changed while copying')
        self.records[ident]=record
        return dict(record)

    def restore(self, record):
        if self.records.get(record['id']) != record or sha(record['path']) != record['archive_sha256']:
            raise RuntimeError('Unowned/changed checkpoint')
        stage = self.image_root/('restore-'+uuid.uuid4().hex)
        import_tree(record['path'],stage)
        for parent,dirs,files in os.walk(stage,followlinks=False):
            os.chown(parent,65534,65534,follow_symlinks=False)
            for name in dirs+files:
                os.chown(Path(parent)/name,65534,65534,follow_symlinks=False)
        retired=self.root/('retired-'+uuid.uuid4().hex)
        self.workspace.rename(retired)
        stage.rename(self.workspace)
        self._scope_cache=None
        if self.scope()!=record['fingerprint']:
            raise RuntimeError('Restoration fingerprint mismatch')

    def delivery(self):
        return dict(path=str(self.workspace),fingerprint=self.scope(),restoration='workspace_files_only')
