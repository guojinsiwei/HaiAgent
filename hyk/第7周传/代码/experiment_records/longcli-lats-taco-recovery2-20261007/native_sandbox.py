"""TACO only: fresh task root; same command driver, isolated without Docker."""
import json
import os
from pathlib import Path
import signal
import subprocess
import time
from common import ROOT,save,export_tree
from client import BudgetStop
from safe_process import run_bounded

def close_owned(directory):
    # Every execute is synchronous in a separate PID namespace. Its init exits
    # before returning; the kernel kills all namespace descendants, even setsid.
    record=Path(directory)/'native-process.json'
    if record.exists():
        r=json.loads(record.read_text());p=Path('/proc')/str(r['pid'])/'stat'
        if p.exists():
            fields=p.read_text().rsplit(')',1)[1].split()
            if fields[19]==r['start_ticks'] and fields[0]!='Z':
                assert os.getpgid(r['pid'])==r['pid']
                os.killpg(r['pid'],signal.SIGKILL)
                for _ in range(30):
                    if not p.exists() or p.read_text().rsplit(')',1)[1].split()[0]=='Z':break
                    time.sleep(.1)
                else:raise RuntimeError('native_process_not_quiescent')
    save(Path(directory)/'quiescence.json',{'stopped':True,'isolation':'per-command PID namespace','time':time.time()})

class Sandbox:
    def __init__(self,row,directory,deadline,health=None):
        self.row=row;self.directory=Path(directory);self.deadline=deadline
        self.health=health or (lambda **kw:None);self.tools=0
        self.prepared=json.loads((ROOT/'native-roots.json').read_text())[row['task']]
        self.state=Path(self.prepared['root'])
        self.driver=(ROOT/'command_driver.py').read_text()
        # /proc is deliberately unavailable. PID namespace exit provides the
        # same escaped-descendant cleanup without ever inspecting host /proc.
        start=self.driver.index('def live_pids():')
        stop=self.driver.index('before=live_pids()')
        self.driver=self.driver[:start]+'def live_pids(): return set()\n'+self.driver[stop:]
        save(self.directory/'isolation.json',{'backend':'native_user_pid_net_chroot',
            'host_memory_cgroup_per_task':False,'process_address_space_gib':3,'cpu_affinity_count':2,
            'writable_paths':['/app','/tmp','/baseline-home','/dev/shm'],
            'fresh_task_root':str(self.state),'network':'none','hidden_tests':False})

    def execute(self,action):
        if self.tools>=600:raise BudgetStop('tool_calls')
        remaining=self.deadline-time.monotonic()
        if remaining<=0:raise BudgetStop('wall_seconds')
        argv=action.get('argv')
        if not isinstance(argv,list) or not argv or any(not isinstance(x,str) for x in argv):raise ValueError('invalid_argv')
        if sum(map(len,argv))>24000:raise ValueError('argv_capacity')
        from posixpath import normpath,join
        cwd=normpath(join('/app',action.get('cwd','.')))
        if cwd!='/app' and not cwd.startswith('/app/'):raise ValueError('invalid_cwd')
        duration=action.get('timeout_seconds',300)
        if isinstance(duration,bool) or not isinstance(duration,(int,float)) or not 0<duration<=300:raise ValueError('invalid_duration')
        stdin=action.get('stdin') or ''
        if not isinstance(stdin,str) or len(stdin)>24000:raise ValueError('stdin_capacity')
        uid=str(self.prepared['uid']);self.tools+=1
        self.health(tool_calls=self.tools,tool_started=time.time())
        body={'argv':argv,'cwd':cwd,'stdin':stdin,'seconds':min(duration,remaining),'output_limit':1024*1024}
        command=['setpriv','--reuid',uid,'--regid',uid,'--clear-groups','unshare',
            '--user','--map-root-user','--pid','--net','--fork','--kill-child=KILL',
            '/usr/bin/python3',str(ROOT/'native_entry.py'),str(self.state),
            json.dumps({'driver':self.driver,'slot':self.prepared['slot']})]
        p=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                           text=True,encoding='utf-8',errors='replace',start_new_session=True)
        try:
            fields=(Path('/proc')/str(p.pid)/'stat').read_text().rsplit(')',1)[1].split()
            save(self.directory/'native-process.json',{'pid':p.pid,'start_ticks':fields[19]})
            out,err=p.communicate(json.dumps(body),timeout=body['seconds']+15)
            if p.returncode:
                save(self.directory/'native-error.json',{'returncode':p.returncode,'stderr':err[-3000:]})
                raise RuntimeError('native_executor_failed')
        finally:
            if p.poll() is None:
                os.killpg(p.pid,signal.SIGKILL)
                try:p.communicate(timeout=2)
                except subprocess.TimeoutExpired:pass
        result=json.loads(out)
        save(self.directory/'tools'/f'{self.tools:04d}.json',{'action':action,'result':result})
        self.health(tool_calls=self.tools,tool_finished=time.time())
        return result

    def close(self):close_owned(self.directory)
    def export(self):return export_tree(self.state/'app',self.directory/'final-source.tar.gz',source_only=True)
