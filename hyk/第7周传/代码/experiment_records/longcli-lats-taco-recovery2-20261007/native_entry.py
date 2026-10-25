"""Trusted entry in fresh user/PID/network namespaces; no host credentials visible."""
import ctypes
import json
import os
from pathlib import Path
import resource
import sys

root=Path(sys.argv[1]).resolve(strict=True)
assert root!=Path('/') and (root/'usr/bin/python3').is_file()
spec=json.loads(sys.argv[2])
cpus=sorted(os.sched_getaffinity(0));slot=spec['slot']
os.sched_setaffinity(0,{cpus[(slot*2)%len(cpus)],cpus[(slot*2+1)%len(cpus)]})
for limit,value in ((resource.RLIMIT_NPROC,128),(resource.RLIMIT_AS,3*2**30),(resource.RLIMIT_CORE,0)):
    resource.setrlimit(limit,(value,value))
os.chroot(root);os.chdir('/app')
libc=ctypes.CDLL(None,use_errno=True)
for cap in range(41):
    if libc.prctl(24,cap,0,0,0) and ctypes.get_errno()!=22:raise OSError('capability drop failed')
class Header(ctypes.Structure):_fields_=[('version',ctypes.c_uint32),('pid',ctypes.c_int)]
class Data(ctypes.Structure):_fields_=[('effective',ctypes.c_uint32),('permitted',ctypes.c_uint32),('inheritable',ctypes.c_uint32)]
header,data=Header(0x20080522,0),(Data*2)()
if libc.capset(ctypes.byref(header),data) or libc.prctl(38,1,0,0,0):raise OSError('privilege drop failed')
env={'PATH':'/usr/local/bin:/usr/bin:/bin','HOME':'/baseline-home','LANG':'C.UTF-8',
     'BASH_ENV':'/dev/null','ENV':'/dev/null','PYTHONDONTWRITEBYTECODE':'1'}
os.execve('/usr/bin/python3',['python3','-c',spec['driver']],env)
