"""Continuous POSIX workspace; immutable file checkpoints only on explicit demand.

Run this local executor inside a disposable sandbox. Path checks do not make shell
commands a security sandbox. No memory/process/network state restoration is claimed.
"""
from dataclasses import asdict
import hashlib
import os
from pathlib import Path, PurePosixPath
import signal
import subprocess
import tempfile
import time
import uuid
from .environment import _copy_workspace, _tree_fingerprint
from .models import CommandSpec, CommandResult
from .lean_progress import normalize_workspace_path


class LiveWorkspace:
    def __init__(self, seed, root, credential_variables=()):
        if os.name != 'posix':
            raise RuntimeError('LiveWorkspace requires Linux/WSL process groups')
        self.seed, self.root = Path(seed).resolve(), Path(root).resolve()
        if not self.seed.is_dir() or self.root.is_relative_to(self.seed):
            raise ValueError('run directory must be outside seed workspace')
        self.root.mkdir(parents=True, exist_ok=False)
        self.workspace = self.root / 'live'
        _copy_workspace(self.seed, self.workspace)
        self.checkpoints = {}
        self.credential_variables = set(credential_variables) | {
            'OPENAI_API_KEY', 'DEEPSEEK_API_KEY', 'DASHSCOPE_API_KEY'}

    def scope(self):
        return _tree_fingerprint(self.workspace)

    def dependency_state(self, paths):
        result = {}
        for raw in paths:
            name = normalize_workspace_path(raw)
            path = self.workspace.joinpath(*PurePosixPath(name).parts)
            try:
                stat = path.lstat()
            except FileNotFoundError:
                result[name] = 'missing'
                continue
            if path.is_symlink():
                result[name] = 'link:' + os.readlink(path)
            elif path.is_file():
                with path.open('rb') as stream:
                    result[name] = 'file:' + str(stat.st_size) + ':' + hashlib.file_digest(stream, 'sha256').hexdigest()
            elif path.is_dir():
                result[name] = 'dir:' + _tree_fingerprint(path)
            else:
                result[name] = 'other'
        return result

    def execute(self, action, deadline):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('work budget exhausted')
        command = CommandSpec(tuple(action['argv']), action.get('purpose', ''),
                              action.get('cwd', '.'), action.get('timeout_seconds', 60), action.get('stdin'))
        cwd = (self.workspace / command.cwd).resolve()
        if not cwd.is_relative_to(self.workspace) or not cwd.is_dir():
            return CommandResult(command, 126, '', 'cwd outside workspace or missing', 0, blocked=True)
        env = {k: v for k, v in os.environ.items() if k.upper() not in {x.upper() for x in self.credential_variables}}
        env['RETRAC_WORKSPACE'] = str(self.workspace)
        started = time.monotonic()
        with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr, tempfile.TemporaryFile() as stdin:
            stdin.write((command.stdin or '').encode()); stdin.seek(0)
            try:
                process = subprocess.Popen(command.argv, cwd=cwd, env=env, stdin=stdin,
                    stdout=stdout, stderr=stderr, start_new_session=True)
            except OSError as error:
                return CommandResult(command, 127, '', type(error).__name__, time.monotonic()-started)
            timed_out = False
            try:
                process.wait(timeout=min(remaining, command.timeout_seconds))
            except subprocess.TimeoutExpired:
                timed_out = True
            finally:
                # Kill descendants even if the leader exited. File-only tasks may
                # not leave a background process mutating a checkpoint afterwards.
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
            def read(stream):
                size = stream.tell(); stream.seek(0)
                if size <= 24000:
                    return stream.read().decode('utf-8', errors='replace'), False
                head = stream.read(12000); stream.seek(-12000, os.SEEK_END)
                return (head + b'\n[output omitted]\n' + stream.read(12000)).decode('utf-8', errors='replace'), True
            out, a = read(stdout); err, b = read(stderr)
            return CommandResult(command, 124 if timed_out else process.returncode, out, err,
                time.monotonic()-started, timed_out=timed_out, output_truncated=a or b)

    def checkpoint(self, label):
        identifier = uuid.uuid4().hex
        target = self.root / ('checkpoint-' + identifier)
        before = self.scope()
        _copy_workspace(self.workspace, target)
        if _tree_fingerprint(target) != before or self.scope() != before:
            raise RuntimeError('workspace changed during checkpoint')
        record = dict(id=identifier, path=str(target), fingerprint=before, label=label,
                      restoration='workspace_files_only')
        self.checkpoints[identifier] = record
        return dict(record)

    def restore(self, record):
        known = self.checkpoints.get(record['id'])
        if known != record:
            raise ValueError('unowned checkpoint')
        source = Path(known['path'])
        if source.is_symlink() or source.parent != self.root or _tree_fingerprint(source) != known['fingerprint']:
            raise RuntimeError('checkpoint integrity failure')
        stage = self.root / ('restore-' + uuid.uuid4().hex)
        _copy_workspace(source, stage)
        if _tree_fingerprint(stage) != known['fingerprint']:
            raise RuntimeError('restore integrity failure')
        # Retain displaced files for audit/recovery; never delete user seed data.
        self.workspace.rename(self.root / ('retired-' + uuid.uuid4().hex))
        stage.rename(self.workspace)

    def delivery(self):
        return dict(path=str(self.workspace), fingerprint=self.scope(), restoration='workspace_files_only')
