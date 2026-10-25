"""Persistent terminal in a new private user/PID/network namespace."""
import ctypes
import fcntl
import os
from pathlib import Path
import resource
import socket
import struct
import sys
import termios
from device_setup import validate_devices

root=Path(sys.argv[1]).resolve(strict=True)
assert root != Path('/') and (root/'usr/bin/python3').is_file()
validate_devices(root)
with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
    flags=struct.unpack('16sh',fcntl.ioctl(sock,0x8913,struct.pack('16sh',b'lo',0))[:18])[1]
    fcntl.ioctl(sock,0x8914,struct.pack('16sh',b'lo',flags|1))
for limit,value in ((resource.RLIMIT_NOFILE,256),(resource.RLIMIT_NPROC,128),
    (resource.RLIMIT_AS,3*2**30),(resource.RLIMIT_CORE,0),(resource.RLIMIT_FSIZE,256*2**20)):
    resource.setrlimit(limit,(value,value))
os.chroot(root)
os.chdir('/app')
libc=ctypes.CDLL(None,use_errno=True)
for cap in range(41):
    if libc.prctl(24,cap,0,0,0) and ctypes.get_errno()!=22:
        raise OSError(ctypes.get_errno(),'capability bounding drop')
class Header(ctypes.Structure):
    _fields_=[('version',ctypes.c_uint32),('pid',ctypes.c_int)]
class Data(ctypes.Structure):
    _fields_=[('effective',ctypes.c_uint32),('permitted',ctypes.c_uint32),('inheritable',ctypes.c_uint32)]
header,data=Header(0x20080522,0),(Data*2)()
if libc.capset(ctypes.byref(header),data) or libc.prctl(38,1,0,0,0):
    raise OSError(ctypes.get_errno(),'privilege drop')
try: os.setsid()
except PermissionError: pass
fcntl.ioctl(0,termios.TIOCSCTTY,0)
env={'PATH':'/usr/local/bin:/usr/bin:/bin','HOME':'/tmp','LANG':'C.UTF-8','TERM':'dumb',
    'PS1':'$ ','PS2':'> ','HISTFILE':'/dev/null','OMP_NUM_THREADS':'2','OPENBLAS_NUM_THREADS':'2',
    'PYTHONDONTWRITEBYTECODE':'1', 'PROMPT_COMMAND':"printf '\\n"+sys.argv[2]+"%s\\n' \"$?\""}
os.execve('/bin/bash',['bash','--noprofile','--norc','-i'],env)
