"""Recreate devices omitted by docker export in a new, private solver root."""
import os
from pathlib import Path
import stat


def prepare_devices(root):
    root = Path(root).resolve(strict=True)
    if root == Path('/') or not (root/'usr/bin/python3').is_file():
        raise ValueError('Expected a private exported solver image')
    dev = root/'dev'
    if dev.is_symlink():
        raise ValueError('Private dev directory must not be a symlink')
    dev.mkdir(exist_ok=True)
    # A regular file is not an acceptable substitute: reads must return EOF,
    # writes must be discarded, and task code must not grow a sink on disk.
    for name, minor in (('null', 3), ('zero', 5), ('random', 8), ('urandom', 9)):
        path = dev/name
        if not path.exists() and not path.is_symlink():
            os.mknod(path, stat.S_IFCHR | 0o666, os.makedev(1, minor))
        info = path.lstat()
        if not stat.S_ISCHR(info.st_mode) or info.st_rdev != os.makedev(1, minor):
            raise ValueError('Invalid private device: '+name)
        os.chmod(path, 0o666)
    return dict(null_character_device=True, mode='0666')


def validate_devices(root):
    p = Path(root)/'dev/null'
    s = p.lstat()
    if (not stat.S_ISCHR(s.st_mode) or s.st_rdev != os.makedev(1, 3)
            or stat.S_IMODE(s.st_mode) != 0o666):
        raise RuntimeError('Solver image /dev/null preflight failed')
