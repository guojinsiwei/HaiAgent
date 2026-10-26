"""Bounded command-clock alignment and timeout log recovery; no success claims."""
import re
import shlex
from pathlib import Path

from .command_paths import command_words, workspace_join


def align_timeout(action, cap):
    repaired = dict(action)
    requested = action.get('timeout_seconds', 60)
    required = requested
    argv = action.get('argv', [])
    script = argv[2] if (len(argv) >= 3 and argv[0].rsplit('/', 1)[-1] in {'bash', 'sh'}
                         and argv[1] in {'-c', '-lc'}) else ''
    if re.search(r'\b(?:qemu-system-[\w-]+|make\s+qemu(?:-gdb)?)\b', script):
        # Literal GNU timeout durations only; no expansion or shell evaluation.
        for number, unit in re.findall(r'\btimeout\s+(\d+(?:\.\d+)?)([smh]?)\b', script):
            duration = float(number) * {'': 1, 's': 1, 'm': 60, 'h': 3600}[unit]
            required = max(required, duration + 10)
    effective = min(required, cap)
    repaired['timeout_seconds'] = effective
    note = dict(requested_seconds=requested, inferred_seconds=required,
                effective_seconds=effective, command_cap=cap,
                inner_limit_exceeds_cap=required > cap,
                task_deadline_unchanged=True)
    return repaired, note


def redirected_logs(action):
    """Literal output targets only. Never recover arbitrary paths from prose."""
    args = action.get('argv', [])
    if not (len(args) >= 3 and args[0].rsplit('/', 1)[-1] in {'bash', 'sh'}
            and args[1] in {'-c', '-lc'} and 'qemu' in args[2]):
        return []
    cwd, words = command_words(action)
    result = []
    for i, word in enumerate(words[:-1]):
        if word not in ('>', '>>') or (i and words[i-1].isdigit()):
            continue  # Never recover descriptor redirection such as 2>&1.
        target = words[i+1]
        if not target or any(c in target for c in '$`*?\n\x00'):
            continue
        if target.startswith('/tmp/'):
            parts = Path(target).parts
            if '..' in parts:
                continue
            name = target
        else:
            if cwd is None and not target.startswith('/app/'):
                continue
            try:
                relative = workspace_join(cwd or '', target)
            except ValueError:
                continue
            if not relative:
                continue
            name = '/app/' + relative
        if name not in result:
            result.append(name)
    return result[-2:]


def snapshot_logs(action, image_root):
    root = Path(image_root).resolve(strict=True)
    state = {}
    for name in redirected_logs(action):
        path = root / name.lstrip('/')
        try:
            resolved = path.resolve(strict=True)
            if not resolved.is_relative_to(root) or path.is_symlink() or not resolved.is_file():
                state[name] = None
                continue
            info = resolved.stat()
            state[name] = (info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        except OSError:
            state[name] = None
    return state


def recover_logs(action, image_root, byte_limit=12000, before=None):
    """Read bounded logs inside the private image, rejecting symlink escapes.

    Called only after a timed-out command. Recovered text is historical task
    data, not proof that a test ran or passed. The timed_out flag stays true.
    """
    root = Path(image_root).resolve(strict=True)
    recovered = []
    remaining = byte_limit
    for name in redirected_logs(action):
        path = root / name.lstrip('/')
        try:
            resolved = path.resolve(strict=True)
            if not resolved.is_relative_to(root) or path.is_symlink() or not resolved.is_file():
                continue
            info = resolved.stat()
            stamp = (info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
            if before is not None and stamp == before.get(name):
                continue  # Never present a stale log as this command's output.
            with resolved.open('rb') as stream:
                size = resolved.stat().st_size
                if size > remaining:
                    stream.seek(-remaining, 2)
                data = stream.read(remaining)
        except OSError:
            continue
        recovered.append(dict(path=name, text=data.decode('utf-8', 'replace'),
                              captured_bytes=len(data), total_bytes=size,
                              partial=size > remaining, task_success=None,
                              freshness='file_metadata_changed' if before is not None else 'unverified'))
        remaining -= len(data)
        if remaining <= 0:
            break
    return recovered
