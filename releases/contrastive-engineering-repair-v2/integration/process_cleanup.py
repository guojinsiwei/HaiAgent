"""Linux command subreaper: clean adopted children, never unrelated processes.

Used only in the explicitly file-only LHTB executor, not the generic HAI runtime.
No argv/environment inspection, global process killing, or task/model replay.
"""
import ctypes
import errno
import os
from pathlib import Path
import signal
import time


def enable_subreaper():
    if os.name != 'posix' or not Path('/proc/self/stat').exists():
        raise RuntimeError('File-only descendant cleanup requires Linux')
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(36, 1, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER
        raise OSError(ctypes.get_errno(), 'Cannot enable command subreaper')
    # This private command helper owns child reaping. Default SIGCHLD preserves
    # exited children as zombies until waitpid; their PIDs cannot be recycled.
    signal.signal(signal.SIGCHLD, signal.SIG_DFL)


def _direct_children():
    rows = []
    for item in Path('/proc').iterdir():
        if not item.name.isdigit():
            continue
        try:
            fields = (item/'stat').read_text().rsplit(')', 1)[1].split()
            if int(fields[1]) == os.getpid():
                rows.append(int(item.name))
        except (OSError, ValueError, IndexError):
            continue
    return rows


def _reap():
    while True:
        try:
            pid, _ = os.waitpid(-1, os.WNOHANG)
        except ChildProcessError:
            return
        if not pid:
            return


def cleanup_children(seconds=3):
    """After root wait: kill only owned, unreaped direct/adopted descendants.

    Use pidfds if this Python build exposes them. Otherwise parent ownership
    plus deferred waitpid pins the child PID even if it exits during the check.
    No concurrent waiter or SIGCHLD auto-reap exists in this private helper.
    """
    until = time.monotonic() + seconds
    killed = 0
    while True:
        _reap()
        children = _direct_children()
        if not children:
            return dict(killed=killed, complete=True, scope='adopted_command_children_only')
        for pid in children:
            fd = None
            try:
                if hasattr(os, 'pidfd_open') and hasattr(signal, 'pidfd_send_signal'):
                    try:
                        fd = os.pidfd_open(pid)
                    except OSError as error:
                        if error.errno not in (errno.ENOSYS, errno.EINVAL):
                            raise
                # Validate parent. A pidfd or our unreaped-child ownership pins identity.
                fields = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
                if int(fields[1]) == os.getpid() and fields[0] != 'Z':
                    if fd is not None:
                        signal.pidfd_send_signal(fd, signal.SIGKILL)
                    else:
                        os.kill(pid, signal.SIGKILL)
                    killed += 1
            except (ProcessLookupError, FileNotFoundError, ChildProcessError):
                pass
            finally:
                if fd is not None:
                    os.close(fd)
        _reap()
        if time.monotonic() >= until:
            raise RuntimeError('Owned command descendants did not terminate; snapshot refused')
        time.sleep(.02)
