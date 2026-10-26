"""Bounded owned subprocess cleanup, including a child stuck after SIGKILL."""
import os
import signal
import subprocess


def _kill(process):
    try:
        if os.name == 'posix':os.killpg(process.pid, signal.SIGKILL)
        else:process.kill()
    except ProcessLookupError:pass


def run_bounded(argv, *, timeout, input=None, text=False, encoding=None, errors=None,
                capture_output=False,stdout=None,stderr=None,stdin=None,check=False):
    # Do not use subprocess.run/with Popen: their timeout/finalizer paths can
    # wait indefinitely for a kernel-uninterruptible child after killing it.
    p=subprocess.Popen(argv,stdin=subprocess.PIPE if input is not None else (stdin if stdin is not None else subprocess.DEVNULL),
        stdout=subprocess.PIPE if capture_output else stdout,stderr=subprocess.PIPE if capture_output else stderr,
        text=text,encoding=encoding if text else None,errors=errors if text else None,
        start_new_session=True)
    try:
        stdout,stderr=p.communicate(input=input,timeout=timeout)
    except BaseException as error:
        _kill(p)
        try:p.communicate(timeout=1)
        except subprocess.TimeoutExpired:pass
        for stream in (p.stdin,p.stdout,p.stderr):
            if stream:
                try:stream.close()
                except OSError:pass
        if isinstance(error,subprocess.TimeoutExpired):error.child_pid=p.pid
        raise error
    result=subprocess.CompletedProcess(argv,p.returncode,stdout,stderr)
    if check:result.check_returncode()
    return result
