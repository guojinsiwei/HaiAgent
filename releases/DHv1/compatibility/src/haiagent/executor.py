"""Single live workspace; no search snapshots, syntax gate or extra verifier."""
from dataclasses import dataclass, asdict, field
import hashlib
import os
from pathlib import Path
import signal
import stat
import subprocess
import threading
import time

SKIP = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "node_modules", ".venv", "venv"}
BASE_ENV = {"PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP", "TMPDIR",
            "HOME", "USER", "USERPROFILE", "LANG", "LC_ALL", "VIRTUAL_ENV", "CONDA_PREFIX"}
CREDENTIALS = {"HAI_API_KEY", "DEEPSEEK_API_KEY", "DASHSCOPE_API_KEY", "OPENAI_API_KEY"}


def workspace_revision(root, *, deadline=None, max_bytes=64_000_000, max_files=5000):
    """Bounded observable source fingerprint, NOT a whole-machine state hash.

    Unknown on incomplete scan or symlinks. Excluded dependency/cache directories
    belong to environment state, which is separately unknown unless host-provided.
    """
    until = min(deadline or float("inf"), time.monotonic() + 2)
    h = hashlib.sha256()
    total = count = 0
    try:
        for directory, dirs, files in os.walk(root, followlinks=False):
            if time.monotonic() >= until:
                return None
            dirs[:] = sorted(d for d in dirs if d not in SKIP)
            if any((Path(directory) / d).is_symlink() for d in dirs):
                return None
            for name in sorted(files):
                path = Path(directory) / name
                if path.is_symlink() or time.monotonic() >= until:
                    return None
                before = path.stat()
                if not stat.S_ISREG(before.st_mode):
                    return None
                count += 1
                total += before.st_size
                if count > max_files or total > max_bytes:
                    return None
                h.update(str(path.relative_to(root)).encode())
                h.update(str(before.st_mode).encode())
                flags = os.O_RDONLY | getattr(os, 'O_NONBLOCK', 0) | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0)
                with os.fdopen(os.open(path, flags), 'rb') as stream:
                    opened = os.fstat(stream.fileno())
                    if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                        return None
                    read_bytes = 0
                    while chunk := stream.read(65536):
                        read_bytes += len(chunk)
                        h.update(chunk)
                        if read_bytes > before.st_size or time.monotonic() >= until:
                            return None
                after = path.stat()
                if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
                    return None
    except OSError:
        return None
    return h.hexdigest()


class BoundedStream:
    def __init__(self, limit):
        self.limit = limit
        self.head = bytearray()
        self.tail = bytearray()
        self.total = 0
        self.complete = False
        self.hash = hashlib.sha256()
        self.lock = threading.Lock()

    def collect(self, stream):
        try:
            while chunk := stream.read(4096):
                with self.lock:
                    self.total += len(chunk)
                    self.hash.update(chunk)
                    n = min(len(chunk), max(0, self.limit * 3 // 4 - len(self.head)))
                    self.head.extend(chunk[:n])
                    self.tail.extend(chunk[n:])
                    if len(self.tail) > self.limit - self.limit * 3 // 4:
                        del self.tail[:len(self.tail) - (self.limit - self.limit * 3 // 4)]
            with self.lock:
                self.complete = True
        except (OSError, ValueError):
            pass
        finally:
            stream.close()

    def view(self):
        with self.lock:
            truncated = self.total > self.limit or not self.complete
            marker = b"\n[output omitted]\n" if truncated else b""
            return ((bytes(self.head) + marker + bytes(self.tail)).decode("utf-8", errors="replace"),
                    truncated, self.hash.hexdigest(), self.total)


@dataclass
class Result:
    exit_code: int | None
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    blocked: bool = False
    output_truncated: bool = False
    duration_seconds: float = 0
    stdout_sha256: str = ""
    stderr_sha256: str = ""
    stdout_bytes: int = 0
    stderr_bytes: int = 0
    background_output_open: bool = False
    recovered_logs: list = field(default_factory=list)
    command_clock: dict = field(default_factory=dict)

    def payload(self):
        return asdict(self)


def stop_tree(process):
    if os.name == "nt":
        if process.poll() is None:
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if process.poll() is None:
        process.kill()
    process.wait(timeout=3)


class LocalExecutor:
    """Requires an externally isolated environment. cwd validation is NOT a sandbox."""
    def __init__(self, task, config):
        self.task, self.config = task, config
        self.root = task.workspace.resolve()

    def execute(self, command, deadline):
        start = time.monotonic()
        cwd = (self.root / command["cwd"]).resolve()
        if not cwd.is_relative_to(self.root) or not cwd.is_dir():
            return Result(126, stderr="cwd escapes workspace or does not exist", blocked=True)
        remaining = deadline - start
        if remaining <= 0:
            return Result(None, stderr="Task deadline exhausted", timed_out=True)
        seconds = min(command["timeout_seconds"], self.config.command_seconds, remaining)
        env = {k: v for k, v in os.environ.items() if k.upper() in BASE_ENV}
        env.update({k: v for k, v in self.task.environment.items() if k.upper() not in CREDENTIALS})
        env["HAI_WORKSPACE"] = str(self.root)
        process = None
        out, err = BoundedStream(self.config.output_bytes // 2), BoundedStream(self.config.output_bytes // 2)
        try:
            process = subprocess.Popen(command["argv"], cwd=cwd, env=env, shell=False,
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       start_new_session=os.name != "nt")
            readers = [threading.Thread(target=out.collect, args=(process.stdout,), daemon=True),
                       threading.Thread(target=err.collect, args=(process.stderr,), daemon=True)]
            for reader in readers:
                reader.start()
            def write_input():
                try:
                    process.stdin.write((command.get("stdin") or "").encode())
                except (OSError, ValueError):
                    pass
                finally:
                    process.stdin.close()
            writer = threading.Thread(target=write_input, daemon=True)
            writer.start()
            timed_out = False
            try:
                process.wait(timeout=max(0.001, seconds - (time.monotonic() - start)))
            except subprocess.TimeoutExpired:
                timed_out = True
                stop_tree(process)
            for reader in readers:
                reader.join(timeout=min(0.1, max(0, deadline - time.monotonic())))
            # A successful launcher may intentionally leave a server alive. Do not
            # kill its process group merely because it inherited the output pipes.
            # Readers remain bounded daemon drains; the task container owns cleanup
            # AFTER external verification. Timeout still terminates the group above.
            background_output_open = any(r.is_alive() for r in readers)
            stdout, cut1, sha1, n1 = out.view()
            stderr, cut2, sha2, n2 = err.view()
            return Result(process.returncode, stdout, stderr, timed_out=timed_out,
                          output_truncated=cut1 or cut2, duration_seconds=time.monotonic() - start,
                          stdout_sha256=sha1, stderr_sha256=sha2, stdout_bytes=n1, stderr_bytes=n2,
                          background_output_open=background_output_open)
        except OSError as exc:
            return Result(127, stderr=f"Executor error: {type(exc).__name__}", duration_seconds=time.monotonic() - start)
        finally:
            if process is not None and process.poll() is None:
                stop_tree(process)
