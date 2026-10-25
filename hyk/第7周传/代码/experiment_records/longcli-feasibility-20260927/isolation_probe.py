"""No real secrets: assert negative access probes inside the task sandbox."""
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent
code = '''import ctypes,json,os,socket
from pathlib import Path
libc=ctypes.CDLL(None,use_errno=True)
class H(ctypes.Structure):
 _fields_=[('version',ctypes.c_uint32),('pid',ctypes.c_int)]
class D(ctypes.Structure):
 _fields_=[('effective',ctypes.c_uint32),('permitted',ctypes.c_uint32),('inheritable',ctypes.c_uint32)]
h=H(0x20080522,0); d=(D*2)(); assert libc.capget(ctypes.byref(h),d)==0
def inaccessible(path):
 try: return not Path(path).exists() or (Path(path).is_dir() and not list(Path(path).iterdir()))
 except PermissionError: return True
r={'capabilities_zero':all(not (v.effective or v.permitted or v.inheritable) for v in d),
 'no_new_privileges':libc.prctl(39,0,0,0,0)==1,
 'host_shared_absent':not Path('/mnt/lizh639').exists(),
 'host_ssh_absent':inaccessible('/root/.ssh'),
 'host_proc_absent':not Path('/proc/1/environ').exists(),
 'docker_socket_absent':not Path('/var/run/docker.sock').exists(),
 'hidden_tests_absent':not Path('/tests').exists(),
 'environment_clean':not any('KEY' in k or 'TOKEN' in k for k in os.environ)}
try: os.chroot('/'); r['cannot_chroot_again']=False
except PermissionError: r['cannot_chroot_again']=True
s=socket.socket(); s.settimeout(2)
try: s.connect(('1.1.1.1',443)); r['network_isolated']=False
except OSError: r['network_isolated']=True
finally: s.close()
try: os.rename('/app','/app-replaced'); r['cannot_replace_workspace_root']=False
except PermissionError: r['cannot_replace_workspace_root']=True
Path('/app/probe-file').unlink(missing_ok=True)
Path('/app/probe-file').write_text('sandbox-write-ok')
r['workspace_writable']=Path('/app/probe-file').read_text()=='sandbox-write-ok'
print(json.dumps(r)); assert all(r.values())
'''
cmd = ['setpriv', '--reuid', '65534', '--regid', '65534', '--clear-groups',
       'unshare', '--user', '--map-root-user', '--pid', '--net', '--fork', '--kill-child=KILL',
       '/mnt/lizh639/envs/swe-eval/bin/python', str(ROOT/'chroot_entry.py'), str(ROOT/'isolation-root'),
       json.dumps({'cwd': '/app', 'argv': ['python3', '-c', code]})]
p = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
print(p.stdout, end='')
print(p.stderr, end='')
assert p.returncode == 0
result = json.loads(p.stdout)
(ROOT/'isolation-result.json').write_text(json.dumps(result, indent=2))
