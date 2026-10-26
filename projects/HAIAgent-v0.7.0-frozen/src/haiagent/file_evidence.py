"""Bounded, conservative file provenance for simple reads, not arbitrary CLI semantics."""
import hashlib
import os
from pathlib import Path
import stat
import time


def fingerprint(path, deadline):
    try:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or before.st_size > 2_000_000:
            return None
        flags = os.O_RDONLY | getattr(os, 'O_NONBLOCK', 0) | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0)
        with os.fdopen(os.open(path, flags), 'rb') as stream:
            opened = os.fstat(stream.fileno())
            if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                return None
            h = hashlib.sha256()
            h.update(str(before.st_mode).encode())
            total = 0
            while block := stream.read(65536):
                total += len(block)
                if total > 2_000_000 or time.monotonic() >= deadline:
                    return None
                h.update(block)
            after = path.lstat()
            if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
                return None
            return h.hexdigest()
    except FileNotFoundError:
        return 'missing'
    except OSError:
        return None


class FileEvidenceTracker:
    def __init__(self, root):
        self.root = root.resolve()
        self.paths = {}  # bounded insertion order, never walks the whole repository

    def select(self, decision):
        argv = decision['argv']
        # No shell parsing, option inference, or interpreting arbitrary model commands.
        if Path(argv[0]).name not in {'cat', 'head', 'tail'} or any(a.startswith('-') for a in argv[1:]):
            return []
        selected = []
        for argument in argv[1:9]:
            candidate = self.root / decision['cwd'] / argument
            if candidate.is_symlink():
                continue
            path = candidate.resolve()
            if not path.is_relative_to(self.root) or len(str(path)) > 512:
                continue
            key = str(path)
            self.paths.pop(key, None)
            self.paths[key] = path
            selected.append(key)
        while len(self.paths) > 32:
            self.paths.pop(next(iter(self.paths)))
        return selected

    def refresh(self, deadline):
        until = min(deadline, time.monotonic() + 0.5)
        return {key: fingerprint(path, until) if time.monotonic() < until and path.resolve() == path else None
                for key, path in self.paths.items()}
