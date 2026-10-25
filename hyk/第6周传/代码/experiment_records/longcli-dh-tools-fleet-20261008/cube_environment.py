"""Same solver/tools, existing private rootfs + user/PID/network namespaces."""
import json,os,signal,subprocess,time
from pathlib import Path
from common import ROOT,save,import_tree
from environment import NativeEnvironment
from docker_environment import DockerEnvironment,COMMAND_DRIVER,TaskBackendError,SharedBackendError
from haiagent.executor import Result
from safe_process import run_bounded
from device_setup import prepare_devices
TEMPLATES=Path('/mnt/lizh639/longcli-planner-v3-10-20261004/templates')
PYTHON='/mnt/lizh639/envs/swe-eval/bin/python'

def live(pid):
    try:return Path('/proc',str(pid),'stat').read_text().rsplit(')',1)[1].split()[0]!='Z'
    except (OSError,IndexError):return False

def close_cube(directory):
    p=directory/'command-process.json'
    if p.exists():
        receipt=json.loads(p.read_text());pid=receipt['pid']
        if live(pid):
            proc=Path('/proc',str(pid))
            assert proc.stat().st_uid in (os.getuid(),65534)
            assert str(directory/'rootfs').encode() in (proc/'cmdline').read_bytes()
            assert os.getpgid(pid)==pid
            os.killpg(pid,signal.SIGKILL)
            for _ in range(50):
                if not live(pid):break
                time.sleep(.1)
            if live(pid):raise SharedBackendError('Owned namespace did not quiesce')
    save(directory/'quiescence.json',{'stopped':True,'time':time.time(),'backend':'private_rootfs_namespaces'})

class CubeExecutor:
    def __init__(self,directory,cpu_ids):self.directory=directory;self.cpu_ids=cpu_ids
    def execute(self,action,deadline,output_limit=24000):
        import posixpath
        cwd=posixpath.normpath(posixpath.join('/app',action.get('cwd','.')))
        if cwd!='/app' and not cwd.startswith('/app/'):return Result(126,stderr='cwd must be inside /app',blocked=True)
        seconds=min(300,float(action.get('timeout_seconds',60)),deadline-time.monotonic())
        if seconds<=0:raise TimeoutError('tool deadline')
        spec={'cwd':'/app','argv':['python3','-I','-c',COMMAND_DRIVER],'cpu_ids':self.cpu_ids}
        argv=['setpriv','--reuid','65534','--regid','65534','--clear-groups',
              'unshare','--user','--map-root-user','--pid','--net','--fork','--kill-child=KILL',
              PYTHON,str(ROOT/'chroot_entry.py'),str(self.directory/'rootfs'),json.dumps(spec)]
        body=dict(argv=action['argv'],cwd=cwd,stdin=action.get('stdin'),seconds=seconds,output_limit=output_limit)
        p=subprocess.Popen(argv,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            text=True,encoding='utf-8',errors='replace',start_new_session=True,close_fds=True)
        save(self.directory/'command-process.json',{'pid':p.pid,'time':time.time()})
        try:out,err=p.communicate(json.dumps(body),timeout=seconds+12)
        except subprocess.TimeoutExpired:
            close_cube(self.directory);p.communicate();raise TaskBackendError('Namespace driver timed out; not retried')
        finally:
            if p.poll() is None:close_cube(self.directory);p.wait(5)
        if p.returncode or len(out)>8*max(1048576,output_limit):
            save(self.directory/('execution-fault-'+str(time.time_ns())+'.json'),{
                'scope':'task','driver_exit_code':p.returncode,'stderr':err[-2000:],
                'automatic_action_retries':0,'command_completion':'unknown','backend':'private_rootfs_namespaces'})
            raise TaskBackendError('Namespace driver failed; diagnostic preserved')
        try:return Result(**json.loads(out))
        except (ValueError,TypeError):raise TaskBackendError('Malformed namespace receipt; not retried')

class CubeEnvironment(DockerEnvironment):
    restore=NativeEnvironment.restore
    def __init__(self,row,directory):
        self.directory=directory
        image=directory/'rootfs';image.mkdir(exist_ok=False)
        template=TEMPLATES/row['family']
        assert (template/'usr/bin/python3').is_file() and not (template/'tests').exists()
        run_bounded(['cp','-a','--reflink=auto',str(template)+'/.',str(image)],timeout=600,check=True)
        app=image/'app'
        if app.exists():
            assert not any(app.iterdir()),'template contains task files'
            app.rmdir()
        import_tree(ROOT/'public'/('starter-'+row['task']+'.tar.gz'),app)
        home=image/'dh-home';home.mkdir(exist_ok=False)
        for tree in (app,home,image/'tmp'):
            for parent,dirs,files in os.walk(tree,followlinks=False):
                os.chown(parent,65534,65534,follow_symlinks=False)
                for name in dirs+files:os.chown(Path(parent)/name,65534,65534,follow_symlinks=False)
        prepare_devices(image)
        NativeEnvironment.__init__(self,image,directory/'checkpoints')
        tasks=json.loads((ROOT/'protocol.json').read_text())['tasks']
        index=next(i for i,r in enumerate(tasks) if r['task']==row['task'])
        allowed=sorted(os.sched_getaffinity(0));ids=allowed[index*2:index*2+2]
        if len(ids)!=2:raise SharedBackendError('Insufficient allocated CPUs')
        self.executor=CubeExecutor(directory,ids)
        check=self.executor.execute({'argv':['sh','-c',
            'set -e; printf clean >/dev/null; test -w /app; test -w "$HOME"; test ! -e /tests; test "$(nproc)" = 2'],
            'timeout_seconds':10},time.monotonic()+15)
        assert check.exit_code==0 and not check.stdout and not check.stderr,'Cube clean shell failed'
        save(directory/'isolation.json',{'backend':'private_rootfs_user_pid_net_namespaces',
            'fresh_home':True,'fresh_workspace':True,'hidden_tests_masked':True,'cpu_ids':ids,
            'process_address_limit_bytes':8*2**30,'aggregate_task_memory_limit':None,
            'shared_container_memory_limit_bytes':16000000000,'memory_limit_not_identical_to_docker':True})
    def close(self):close_cube(self.directory)
