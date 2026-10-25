"""Shared process budget, log preservation and workspace delivery for both arms."""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys

ROOT = Path('/tmp/bestfgs/harbor-task')
LOGROOT = Path('/logs/agent/runtime')
WORKSPACE = Path('/app')


def deliver(source, seed, target):
    """Copy the chosen snapshot AND propagate deletions, without following links."""
    source, seed, target = map(Path, (source, seed, target))
    if not source.is_dir() or source.is_symlink() or target.is_symlink():
        raise ValueError('Unsafe delivery root')
    if source == target or target in source.parents or source in target.parents:
        raise ValueError('Overlapping delivery roots')
    # Only remove paths known to have existed in the seed and removed in candidate.
    # Ignored task caches and external OS state are not treated as snapshot state.
    def entries(root):
        result = []
        for base, dirs, files in os.walk(root, followlinks=False):
            dirs[:] = [d for d in dirs if d != '.git']
            result.extend(Path(base, n).relative_to(root) for n in dirs + files)
        return result
    removed = [p for p in entries(seed) if not (source / p).exists() and not (source / p).is_symlink()]
    for relative in sorted(removed, key=lambda p: len(p.parts), reverse=True):
        dest = target / relative
        if any((target / Path(*relative.parts[:i])).is_symlink() for i in range(1, len(relative.parts))):
            raise ValueError('Delivery parent became a symlink')
        if dest.is_symlink() or dest.is_file():
            dest.unlink()
        elif dest.is_dir():
            try:
                dest.rmdir()
            except OSError:
                pass
    for base, dirs, files in os.walk(source, followlinks=False):
        dirs[:] = [d for d in dirs if d != '.git']
        relative = Path(base).relative_to(source)
        destdir = target / relative
        if destdir.is_symlink() or (destdir.exists() and not destdir.is_dir()):
            destdir.unlink()
        destdir.mkdir(parents=True, exist_ok=True)
        for name in dirs + files:
            item, dest = Path(base, name), destdir / name
            if item.is_symlink():
                if dest.is_dir() and not dest.is_symlink():
                    raise ValueError('Refusing to replace a nonempty task directory with a link')
                if dest.exists() or dest.is_symlink():
                    dest.unlink()
                dest.symlink_to(os.readlink(item))
            elif item.is_file():
                if dest.is_symlink():
                    dest.unlink()
                elif dest.is_dir():
                    # Exact task-local type replacement, not a copy INTO the
                    # old directory. Never follow parent links outside /app.
                    if target.resolve() not in dest.resolve().parents:
                        raise ValueError('Delivery path escaped task workspace')
                    shutil.rmtree(dest)
                shutil.copy2(item, dest)


def main():
    payload = json.loads(Path('/installed-agent/input.json').read_text())
    method = payload['method']
    if method not in ('raw', 'bestfgs') or ROOT.exists():
        raise ValueError('Invalid method or duplicate attempt')
    ROOT.mkdir(parents=True)
    env = dict(os.environ, PYTHONPATH='/installed-agent/src', PYTHONUNBUFFERED='1')
    command = [sys.executable, '-m', 'bestfgs.raw_baseline' if method == 'raw' else 'bestfgs',
               *payload['args'], '--goal', payload['instruction'], '--workspace', str(WORKSPACE),
               '--run-root', str(ROOT), '--constraint',
               'Work only in this isolated task container. Do not read /solution or hidden verifier tests. '
               'Snapshot/restore covers the /app task workspace only; external OS or service state is not restored.']
    timed_out = False
    with Path('/logs/agent/agent-result.json').open('w') as output, Path('/logs/agent/progress.log').open('w') as log:
        process = subprocess.Popen(command, stdout=output, stderr=log, env=env, start_new_session=True)
        try:
            code = process.wait(timeout=float(payload['timeout']))
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGTERM)
            try:
                code = process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                code = process.wait()
    checkpoint = ROOT / 'search_checkpoint.json'
    status = {'method': method, 'exit_code': code, 'wall_time_limit_hit': timed_out,
              'delivery_ok': False, 'official_success': None}
    if checkpoint.is_file():
        result = json.loads(checkpoint.read_text())
        source = Path(result['best_workspace']).resolve()
        if not source.is_relative_to(ROOT.resolve()):
            raise ValueError('Candidate escaped runtime directory')
        deliver(source, ROOT / 'root', WORKSPACE)
        status.update(delivery_ok=True, runtime_version=result.get('runtime_version'),
                      blocking_memory_mode=result.get('blocking_memory_mode'),
                      stop_reason=result.get('stop_reason'))
    # Snapshot trees can be huge. Persist evidence files, not every mutable copy.
    # The official verifier sees the delivered /app before the container is deleted.
    LOGROOT.mkdir(parents=True, exist_ok=True)
    for source in ROOT.iterdir():
        if source.is_file() and source.suffix in ('.json','.jsonl','.log','.patch'):
            shutil.copy2(source, LOGROOT/source.name)
    Path('/logs/agent/transport-status.json').write_text(json.dumps(status, indent=2))
    return 0 if status['delivery_ok'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
