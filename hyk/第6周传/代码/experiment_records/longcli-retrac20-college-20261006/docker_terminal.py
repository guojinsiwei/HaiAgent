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
    p=subprocess.run(['docker',*map(str,args)],capture_output=True,text=True,
                     encoding='utf-8',errors='replace',timeout=seconds)
    if check and p.returncode:raise RuntimeError('Docker operation failed: '+p.stderr[-500:])
    return p

def cleanup_owned(name,job,preserve_to=None):
    p=docker('inspect',name,'--format','{{json .Config.Labels}}',check=False)
    if p.returncode:return
    labels=json.loads(p.stdout)
    assert labels.get('experiment')==ROOT.name and labels.get('job')==job
    if preserve_to is not None:
        target=Path(preserve_to);target.mkdir(exist_ok=True)
        running=docker('inspect',name,'--format','{{.State.Running}}').stdout.strip()=='true'
        paused=docker('inspect',name,'--format','{{.State.Paused}}').stdout.strip()=='true'
        if running and not paused:docker('pause',name)
        try:docker('cp',name+':/app/.',str(target),seconds=600)
        except Exception:
            # Never delete a failed trial's only source snapshot.
            if running:docker('unpause',name,check=False)
            docker('stop','-t','2',name,check=False)
            raise
        if running:docker('unpause',name,check=False)
    docker('stop','-t','2',name,check=False)
    stopped=docker('inspect',name,'--format','{{.State.Running}}').stdout.strip()
    assert stopped=='false','Container still running; do not claim processes stopped'
    docker('rm','-v',name)

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
               '--mount','type=volume,destination=/app',
               '--tmpfs','/tmp:rw,exec,size=2g','--tmpfs','/logs:rw,size=128m',
               '-w','/app','--entrypoint','/usr/bin/env',image,'-i',
               'PATH=/usr/local/bin:/usr/bin:/bin','HOME=/tmp','LANG=C.UTF-8',
               'TERM=xterm-256color','PYTHONDONTWRITEBYTECODE=1','OMP_NUM_THREADS=2',
               'OPENBLAS_NUM_THREADS=2','prlimit','--as=3221225472:3221225472','--','sleep','infinity')
        docker('cp',str(BASE/'public'/row['task'])+'/.',self.name+':/app/')
        import docker as sdk
        self.client=sdk.from_env(timeout=60)
        container=self.client.containers.get(self.name)
        Session=native_modules()
        self.session=Session('retrac',LimitedContainer(container),commands_path=self.directory/'keystrokes.txt',disable_recording=True)
        self.session.start()
        sys.path.insert(0,str(ROOT/'retrac/src'))
        from retrac.longcli import TmuxTerminal
        self.terminal=TmuxTerminal(self.session,max_duration=300)

    def observe(self):return self.terminal.observe()
    def execute(self,keystrokes,duration):return self.terminal.execute(keystrokes,duration)
    def close(self):
        if self.closed:return
        # Freeze writers before copying. Preserve the immutable host copy before
        # removing ONLY this task's anonymous app volume/container.
        docker('pause',self.name)
        try:docker('cp',self.name+':/app/.',str(self.app),seconds=600)
        finally:docker('unpause',self.name,check=False)
        cleanup_owned(self.name,self.job)
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
        p=subprocess.run(['docker','exec','-i',self.container.name,'tar','-x','--no-same-owner','-C','/tmp'],
                         input=data,capture_output=True,timeout=60)
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
