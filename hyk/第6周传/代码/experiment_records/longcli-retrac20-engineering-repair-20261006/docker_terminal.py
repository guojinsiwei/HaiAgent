"""Owned Docker sandbox; load the pinned upstream tmux implementation unchanged."""
import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import types
from common import ROOT, save
from safe_process import run_bounded

BASE=Path('/var/tmp/lizh639-longcli-dh-raw-full20-20261004')

def native_modules():
    upstream=ROOT/'upstream'
    # Avoid the upstream eager agent factory (which imports unrelated agents).
    # These are package namespaces only: every runtime class is real pinned code.
    for name,relative in [('terminal_bench','terminal_bench'),
                          ('terminal_bench.terminal','terminal_bench/terminal'),
                          ('terminal_bench.agents','terminal_bench/agents')]:
        if name not in sys.modules:
            package=types.ModuleType(name);package.__path__=[str(upstream/relative)]
            sys.modules[name]=package
    return importlib.import_module('terminal_bench.terminal.tmux_session').TmuxSession

def docker(*args,check=True,seconds=90):
    p=run_bounded(['docker',*map(str,args)],capture_output=True,text=True,
                     encoding='utf-8',errors='replace',timeout=seconds)
    if check and p.returncode:raise RuntimeError('Docker operation failed: '+p.stderr[-500:])
    return p

def cleanup_owned(name,job,preserve_to=None):
    from docker_cleanup import cleanup
    return cleanup(docker,name,job,preserve_to)

class PersistentTerminal:
    def __init__(self,row,directory,cpus,logger,job):
        self.directory=Path(directory);self.job=job;self.logger=logger
        import hashlib
        self.name='retrac-'+hashlib.sha256((ROOT.name+job).encode()).hexdigest()[:20]
        self.closed=False;self.session=None
        save(self.directory/'container.json',{'name':self.name,'job':job,'experiment':ROOT.name})
        self.app=self.directory/'app';self.app.mkdir(exist_ok=False)
        image=json.loads((ROOT/'protocol.json').read_text())['base_images'][row['family']]['id']
        # No key, host root, socket, tests, or shared state is mounted into /app.
        # read-only toolchain mirrors the protected Cube exported rootfs.
        docker('run','-d','--name',self.name,'--label','experiment='+ROOT.name,'--label','job='+job,
               '--network','none','--cap-drop','ALL','--security-opt','no-new-privileges',
               '--read-only','--pids-limit','128','--cpuset-cpus',','.join(map(str,cpus)),
               '--cpus','2',
               '--ulimit','nofile=256:256','--ulimit','fsize=268435456:268435456','--ulimit','core=0:0',
               '--mount','type=volume,destination=/app,volume-nocopy',
               '--tmpfs','/tmp:rw,exec,size=2g','--tmpfs','/logs:rw,size=128m',
               '-w','/app','--entrypoint','/usr/bin/env',image,'-i',
               'PATH=/usr/local/bin:/usr/bin:/bin','HOME=/tmp','LANG=C.UTF-8',
               'TERM=xterm-256color','PYTHONDONTWRITEBYTECODE=1','OMP_NUM_THREADS=2',
               'OPENBLAS_NUM_THREADS=2','prlimit','--as=3221225472:3221225472','--','sleep','infinity')
        self.copy_public(row)
        self.verify_writable()
        import docker as sdk
        self.client=sdk.from_env(timeout=60)
        container=self.client.containers.get(self.name)
        Session=native_modules()
        self.session=Session('retrac',LimitedContainer(container),commands_path=self.directory/'keystrokes.txt',disable_recording=True)
        self.session.start()
        sys.path.insert(0,str(ROOT/'retrac/src'))
        from retrac.longcli import TmuxTerminal
        self.terminal=TmuxTerminal(self.session,max_duration=300)

    def copy_public(self,row):
        # No image-seeded uid1016 directory and no inherited host ownership.
        # Only pinned public input is copied. Solver still has zero capabilities.
        import io,tarfile
        source=BASE/'public'/row['task']
        data=io.BytesIO()
        def owner(member):
            member.uid=member.gid=0;member.uname=member.gname='root'
            return member
        with tarfile.open(fileobj=data,mode='w',dereference=False) as archive:
            for path in sorted(source.iterdir()):
                archive.add(path,arcname=path.name,filter=owner)
        result=run_bounded(['docker','exec','-i',self.name,'tar','-x',
                               '--no-same-owner','-C','/app'],input=data.getvalue(),
                              capture_output=True,timeout=120,text=False)
        if result.returncode:raise RuntimeError('Pinned public source transfer failed')

    def verify_writable(self):
        # Exercise every real nested directory before the first model request.
        # Exclusive temporary probe files are removed; starter contents unchanged.
        code=('import os,tempfile,json\nfrom pathlib import Path\n'
              'dirs=[Path(p) for p,ds,fs in os.walk("/app",followlinks=False)]\n'
              'assert all(p.stat().st_uid==0 and p.stat().st_gid==0 for p in dirs)\n'
              'for path in dirs:\n'
              ' fd,name=tempfile.mkstemp(prefix=".retrac-write-probe-",dir=path)\n'
              ' os.close(fd);os.unlink(name)\n'
              'print(json.dumps({"nested_directories":len(dirs),"writable":True}))')
        result=docker('exec',self.name,'python3','-c',code,seconds=120)
        save(self.directory/'workspace-acceptance.json',json.loads(result.stdout))
        self.writable_workspace_verified=True

    def observe(self):return self.terminal.observe()
    def execute(self,keystrokes,duration):return self.terminal.execute(keystrokes,duration)
    def close(self):
        if self.closed:return
        receipt=cleanup_owned(self.name,self.job,self.app)
        if receipt.get('snapshot'):self.app=Path(receipt['snapshot'])
        elif receipt['state']=='already_absent':raise RuntimeError('Task container vanished before final source snapshot')
        self.closed=True
        if hasattr(self,'client'):self.client.close()

class LimitedContainer:
    """Docker has no --ulimit as; apply Linux prlimit to every trusted exec.

    The real tmux server and all descendant model commands inherit this limit.
    Archive transport and the upstream tmux algorithm are otherwise untouched.
    """
    def __init__(self,container):self.container=container
    def __getattr__(self,name):return getattr(self.container,name)
    def put_archive(self,path,data):
        # Docker archive API refuses tmpfs under a read-only rootfs. Deliver
        # ONLY the pinned public timestamp helper through exec stdin instead.
        assert path=='/tmp'
        import io,tarfile
        with tarfile.open(fileobj=io.BytesIO(data)) as archive:
            members=archive.getmembers()
            assert len(members)==1 and members[0].isfile() and members[0].name=='get-asciinema-timestamp.sh'
            expected=(ROOT/'upstream/terminal_bench/terminal/get-asciinema-timestamp.sh').read_bytes()
            assert archive.extractfile(members[0]).read()==expected
        p=run_bounded(['docker','exec','-i',self.container.name,'tar','-x','--no-same-owner','-C','/tmp'],
                         input=data,capture_output=True,timeout=60,text=False)
        if p.returncode:raise RuntimeError('Native timestamp helper transport failed')
        return True
    def exec_run(self,cmd,**kwargs):
        # Same conversion Docker SDK itself performs for string argv; this is
        # not shell evaluation (the upstream mkdir transport uses a string).
        if isinstance(cmd,str):
            import shlex
            cmd=shlex.split(cmd)
        assert isinstance(cmd,list)
        return self.container.exec_run(['prlimit','--as=3221225472:3221225472','--',*cmd],**kwargs)
