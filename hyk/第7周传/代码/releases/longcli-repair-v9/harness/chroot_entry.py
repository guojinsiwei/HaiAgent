"""Trusted launcher, invoked inside new user, PID and network namespaces.

No mount namespace is required. Rootfs is a private image export, not a bind of host /.
Drop all capabilities and privilege gain after chroot, before executing untrusted code.
"""
import ctypes
import json
import os
from pathlib import Path
import resource
import sys
from device_setup import validate_devices

def main():
    root = Path(sys.argv[1]).resolve(strict=True)
    spec = json.loads(sys.argv[2])
    if not (root / 'usr/bin/python3').exists() or root == Path('/'):
        raise RuntimeError('Invalid private image root')
    validate_devices(root)
    cpus = sorted(os.sched_getaffinity(0))[:2]
    os.sched_setaffinity(0, cpus)
    resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))
    resource.setrlimit(resource.RLIMIT_NPROC, (128, 128))
    resource.setrlimit(resource.RLIMIT_AS, (3 * 2**30, 3 * 2**30))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_FSIZE, (256 * 2**20, 256 * 2**20))
    # Only stdin/stdout/stderr survive Popen(close_fds=True); none are credential streams.
    os.chroot(root)
    os.chdir(spec['cwd'])
    libc = ctypes.CDLL(None, use_errno=True)
    for cap in range(41):
        if libc.prctl(24, cap, 0, 0, 0) != 0 and ctypes.get_errno() != 22:
            raise OSError(ctypes.get_errno(), 'Cannot drop bounding capability')
    class Header(ctypes.Structure):
        _fields_ = [('version', ctypes.c_uint32), ('pid', ctypes.c_int)]
    class Data(ctypes.Structure):
        _fields_ = [('effective', ctypes.c_uint32), ('permitted', ctypes.c_uint32), ('inheritable', ctypes.c_uint32)]
    header = Header(0x20080522, 0)
    data = (Data * 2)()
    if libc.capset(ctypes.byref(header), data) != 0:
        raise OSError(ctypes.get_errno(), 'Cannot clear capabilities')
    if libc.prctl(38, 1, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), 'Cannot set no_new_privs')
    env = {'PATH': '/usr/local/bin:/usr/bin:/bin', 'HOME': '/tmp', 'LANG': 'C.UTF-8',
           'PYTHONDONTWRITEBYTECODE': '1', 'OMP_NUM_THREADS': '2', 'OPENBLAS_NUM_THREADS': '2'}
    os.execvpe(spec['argv'][0], spec['argv'], env)

if __name__ == '__main__':
    main()
