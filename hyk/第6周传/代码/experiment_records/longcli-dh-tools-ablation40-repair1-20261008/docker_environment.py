"""Fresh isolated official task container; DH state/checkpoint interfaces retained."""
import json
import os
from pathlib import Path
import posixpath
import shutil
import subprocess
import time
import uuid
from dataclasses import replace
from common import ROOT,import_tree,export_tree,sha,save
from environment import NativeEnvironment
from haiagent.executor import Result
from safe_process import run_bounded

BASE=Path('/var/tmp/lizh639-longcli-dh-raw-full20-20261004')

class TaskBackendError(RuntimeError):
    """Only the owned task is lost; never promote this to a fleet failure."""

class SharedBackendError(RuntimeError):
    """The Docker daemon cannot be verified; stop admitting new work."""

def execution_fault(name,directory,returncode,stderr):
    # Never repeat an action: it may already have changed files before the driver died.
    observed=docker('inspect',name,check=False,seconds=10)
    if observed.returncode==0:
        state=json.loads(observed.stdout)[0]['State']
        scope='task';running=state.get('Running',False)
    else:
        daemon=docker('info','--format','{{.ServerVersion}}',check=False,seconds=10)
        scope='shared' if daemon.returncode else 'task';running=False
        state={}
    memory_events={}
    if running:
        try:
            counters=docker('exec',name,'cat','/sys/fs/cgroup/memory.events',check=False,seconds=5)
            if counters.returncode==0:
                memory_events={k:int(v) for k,v in (line.split() for line in counters.stdout.splitlines())}
        except (OSError,ValueError,TimeoutError,subprocess.TimeoutExpired):pass
    receipt={'scope':scope,'driver_exit_code':returncode,'container_running':running,
             'oom_killed':state.get('OOMKilled'), 'stderr':stderr[-2000:],
             'memory_events':memory_events,
             'time':time.time(),'command_completion':'unknown','automatic_action_retries':0}
    if directory:save(directory/('execution-fault-'+str(time.time_ns())+'.json'),receipt)
    if scope=='shared':raise SharedBackendError('Docker daemon unavailable; diagnostic receipt preserved')
    if not running:raise TaskBackendError('Owned task container stopped; diagnostic receipt preserved')
    return receipt

def docker(*args,check=True,seconds=60,input=None):
    p=run_bounded(['docker',*map(str,args)],capture_output=True,text=True,encoding='utf-8',
                  errors='replace',timeout=seconds,input=input)
    if check and p.returncode:raise SharedBackendError('Docker operation failed: '+p.stderr[-300:])
    return p

COMMAND_DRIVER=r'''
import json,os,signal,subprocess,sys,tempfile,time
c=json.load(sys.stdin);start=time.monotonic();timeout=False
def live_pids():
    result=set()
    for name in os.listdir('/proc'):
        if not name.isdigit():continue
        try:
            with open('/proc/'+name+'/stat') as f:state=f.read().rsplit(')',1)[1].split()[0]
            if state!='Z':result.add(int(name))
        except (OSError,IndexError):pass
    return result
before=live_pids()
with tempfile.TemporaryFile() as out,tempfile.TemporaryFile() as err:
    try:
        p=subprocess.Popen(c['argv'],cwd=c['cwd'],stdin=subprocess.PIPE,stdout=out,stderr=err,
                           start_new_session=True,env=dict(os.environ,BASH_ENV='/dev/null',ENV='/dev/null'))
    except OSError as error:
        print(json.dumps(dict(exit_code=127 if error.errno==2 else 126,stdout='',
            stderr=str(error),timed_out=False,output_truncated=False,duration_seconds=time.monotonic()-start)))
        raise SystemExit(0)
    try:
        p.communicate((c.get('stdin') or '').encode(),timeout=c['seconds'])
    except subprocess.TimeoutExpired:
        timeout=True
    finally:
        try:os.killpg(p.pid,signal.SIGKILL)
        except ProcessLookupError:pass
    p.wait(timeout=3)
    # /proc here belongs ONLY to this owned task container. Stop descendants
    # that escaped the command's process group via setsid/double-fork too.
    for _ in range(20):
        extra=live_pids()-before
        if not extra:break
        for pid in extra:
            try:os.kill(pid,signal.SIGKILL)
            except ProcessLookupError:pass
        time.sleep(.02)
    if live_pids()-before:raise RuntimeError('Command descendants did not quiesce')
    def read(f):
        n=f.tell();limit=c['output_limit'];f.seek(0)
        if n<=limit:return f.read().decode('utf-8','replace'),False
        a=f.read(limit//2);f.seek(-limit//2,2)
        return (a+b'\n[output truncated]\n'+f.read(limit//2)).decode('utf-8','replace'),True
    a,ta=read(out);b,tb=read(err)
    print(json.dumps(dict(exit_code=124 if timeout else p.returncode,stdout=a,stderr=b,
        timed_out=timeout,output_truncated=ta or tb,duration_seconds=time.monotonic()-start)))
'''

def close_owned(directory):
    receipt=directory/'container.json'
    if not receipt.exists():return
    info=json.loads(receipt.read_text());name=info['name']
    p=docker('inspect',name,check=False,seconds=10)
    if p.returncode and 'no such' in p.stderr.lower():return
    assert p.returncode==0
    data=json.loads(p.stdout)[0]
    assert data['Config']['Labels']['experiment']==ROOT.name
    assert data['Config']['Labels']['job']==info['job']
    if data['State']['Running']:docker('kill',name,seconds=15)
    assert docker('inspect',name,'--format','{{.State.Running}}',seconds=10).stdout.strip()=='false'
    save(directory/'quiescence.json',{'stopped':True,'name':name,'time':time.time()})
    docker('rm',name,seconds=15)

class DockerExecutor:
    def __init__(self,name,directory=None):self.name=name;self.directory=directory
    def execute(self,action,deadline,output_limit=24000):
        cwd=posixpath.normpath(posixpath.join('/app',action.get('cwd','.')))
        if cwd!='/app' and not cwd.startswith('/app/'):
            return Result(126,stderr='cwd must be inside /app',blocked=True)
        seconds=min(300,float(action.get('timeout_seconds',60)),deadline-time.monotonic())
        if seconds<=0:raise TimeoutError('tool deadline')
        body=dict(argv=action['argv'],cwd=cwd,stdin=action.get('stdin'),seconds=seconds,output_limit=output_limit)
        p=docker('exec','-i',self.name,'python3','-I','-c',COMMAND_DRIVER,
                 input=json.dumps(body),seconds=seconds+12,check=False)
        if p.returncode:
            execution_fault(self.name,self.directory,p.returncode,p.stderr)
            # A live container does not imply escaped descendants are quiescent.
            # Stop this task before another action whenever the wrapper dies.
            raise TaskBackendError('Command driver failed; result/diagnostic receipt preserved')
        try:return Result(**json.loads(p.stdout))
        except (ValueError,TypeError):
            execution_fault(self.name,self.directory,125,'Malformed execution receipt: '+p.stderr[-1000:])
            raise TaskBackendError('Malformed command receipt; task stopped without retry')

class DockerEnvironment(NativeEnvironment):
    def execute(self,action,deadline):
        # Keep physical tool implementation out of command identities and prompts.
        spec=action.get('_native_tool',{})
        if spec.get('tool') not in ('inspect_code','edit_code'):
            return super().execute(action,deadline)
        from bestfgs.code_tools import TOOL_DRIVER
        from bestfgs.models import CommandSpec
        physical=dict(action,argv=['python3','-I','-c',TOOL_DRIVER])
        result=super().execute(physical,deadline)
        visible=CommandSpec(tuple(action['argv']),action.get('purpose',''),action.get('cwd','.'),
                            action.get('timeout_seconds',60),action.get('stdin'))
        return replace(result,command=visible)

    def __init__(self,row,directory):
        self.directory=directory;self.image_root=directory
        self.workspace=directory/'workspace'
        import_tree(BASE/('starter-'+row['task']+'.tar.gz'),self.workspace)
        self.root=directory/'checkpoints';self.root.mkdir()
        self.records={};self._scope_cache=None;self.outcome_reliability=False
        home=directory/'home';home.mkdir()
        scratch=directory/'tmp';scratch.mkdir()
        assert (self.workspace/'INSTRUCTION.md').is_file()
        assert docker('image','inspect',row['image'],'--format','{{.Id}}').stdout.strip()==row['image_id']
        name='dh-large20-'+uuid.uuid4().hex[:16]
        # CPU quotas alone do not constrain nproc: make -j$(nproc) could spawn
        # host-wide compiler jobs inside an 8 GiB task. Give each fixed task two
        # visible CPUs, matching its existing 2-CPU allocation without extra budget.
        tasks=json.loads((ROOT/'protocol.json').read_text())['tasks']
        index=next(i for i,r in enumerate(tasks) if r['task']==row['task'])
        methods=json.loads((ROOT/'protocol.json').read_text())['methods']
        method=next((m for m in methods if directory.name.startswith(m+'--')),methods[0])
        slot=index*len(methods)+methods.index(method)
        allowed=sorted(os.sched_getaffinity(0))
        if len(allowed)<2*len(tasks)*len(methods):raise SharedBackendError('Insufficient CPUs for fixed isolated allocation')
        cpuset=','.join(str(x) for x in allowed[slot*2:slot*2+2])
        save(directory/'container.json',{'name':name,'job':directory.name,'image_id':row['image_id']})
        docker('run','-d','--name',name,'--label','experiment='+ROOT.name,'--label','job='+directory.name,
            '--user',f'{os.getuid()}:{os.getgid()}','--cpus','2','--cpuset-cpus',cpuset,'--memory','8g','--pids-limit','256',
            '--cap-drop','ALL','--security-opt','no-new-privileges','--network','none',
            '--mount',f'type=bind,src={self.workspace},dst=/app',
            '--mount',f'type=bind,src={home},dst=/dh-home',
            '--mount',f'type=bind,src={scratch},dst=/tmp',
            '--mount',f'type=bind,src={ROOT / "empty-tests"},dst=/tests,readonly',
            '-e','HOME=/dh-home','-e','BASH_ENV=/dev/null','-e','ENV=/dev/null',
            '-w','/app',row['image_id'],'sleep','infinity')
        observed=json.loads(docker('inspect',name).stdout)[0]
        assert observed['HostConfig']['Memory']==8*2**30 and observed['HostConfig']['NanoCpus']==2*10**9
        assert next(m for m in observed['Mounts'] if m['Destination']=='/tests')['RW'] is False
        assert all(Path(m['Source']).is_relative_to(directory) for m in observed['Mounts'] if m['RW'])
        save(directory/'isolation.json',{'hidden_tests_masked':True,'fresh_home':True,'fresh_workspace':True,
            'memory_bytes':observed['HostConfig']['Memory'],'nano_cpus':observed['HostConfig']['NanoCpus'],
            'cpuset_cpus':observed['HostConfig']['CpusetCpus'],
            'network':observed['HostConfig']['NetworkMode'],'mounts':observed['Mounts']})
        self.executor=DockerExecutor(name,directory)
        p=self.executor.execute({'argv':['sh','-c','set -e; printf clean >/dev/null; test -w /app; test -w "$HOME"; test -z "$(ls -A /tests)"; printf scratch-ok > /tmp/preflight; test "$(cat /tmp/preflight)" = scratch-ok'],
            'timeout_seconds':10},time.monotonic()+15)
        assert p.exit_code==0 and not p.stdout and not p.stderr,'Clean first command preflight failed'

    def probe(self,script,stdin=None):
        p=self.executor.execute({'argv':['python3','-I','-c',script],'stdin':stdin,'timeout_seconds':90},
                                time.monotonic()+90,output_limit=1048576)
        if p.exit_code or p.output_truncated:raise RuntimeError('Isolated observation failed')
        return p.stdout.strip()

    def restore(self,record):
        assert self.records.get(record['id'])==record and sha(record['path'])==record['archive_sha256']
        stage=self.root/('restore-'+uuid.uuid4().hex);import_tree(record['path'],stage)
        retired=self.root/('retired-'+uuid.uuid4().hex);retired.mkdir()
        # Preserve mount inode and all replaced user files; operate only on this task's children.
        assert self.workspace.resolve()==self.directory.resolve()/'workspace'
        for p in self.workspace.iterdir():p.rename(retired/p.name)
        for p in stage.iterdir():p.rename(self.workspace/p.name)
        self._scope_cache=None
        assert self.scope()==record['fingerprint'],'Restoration fingerprint mismatch'

    def close(self):close_owned(self.directory)
