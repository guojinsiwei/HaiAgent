"""Reversible CLI states include every writable mount, not just chat history."""
import json
import os
from pathlib import Path
import shutil
import time
import uuid
from common import ROOT,save,sha,import_tree,export_tree
from safe_process import run_bounded
from client import BudgetStop,clip_bytes

BASE=Path('/var/tmp/lizh639-longcli-dh-raw-full20-20261004')

def docker(*args,seconds=30,check=True,input=None):
    p=run_bounded(['docker',*map(str,args)],timeout=seconds,input=input,text=True,
                  encoding='utf-8',errors='replace',capture_output=True)
    if check and p.returncode:
        save(ROOT/('docker-failure-'+uuid.uuid4().hex+'.json'),
             {'operation':str(args[0]),'returncode':p.returncode,'stderr':p.stderr[-4000:],
              'time':time.time()})
        raise RuntimeError('docker_'+str(args[0])+'_failed')
    return p

def close_owned(directory):
    p=Path(directory)/'container.json'
    if not p.exists():return
    r=json.loads(p.read_text());name=r['name']
    q=docker('inspect',name,check=False,seconds=8)
    if q.returncode and 'no such' in q.stderr.lower():return
    if q.returncode:raise RuntimeError('container_inspect_failed')
    x=json.loads(q.stdout)[0]
    assert x['Config']['Labels'].get('experiment')==ROOT.name
    assert x['Config']['Labels'].get('job')==Path(directory).name
    if x['State']['Running']:docker('kill',name,seconds=12)
    assert docker('inspect',name,'--format','{{.State.Running}}',seconds=8).stdout.strip()=='false'
    docker('rm',name,seconds=12)
    save(Path(directory)/'quiescence.json',{'stopped':True,'container':name,'time':time.time()})

class Sandbox:
    def __init__(self,row,directory,deadline,health=None):
        self.row=row;self.directory=Path(directory);self.deadline=deadline
        self.health=health or (lambda **_:None);self.tools=0;self.current=None;self.records={}
        self.state=self.directory/'live';self.state.mkdir()
        import_tree(BASE/('starter-'+row['task']+'.tar.gz'),self.state/'app')
        for n in ('home','tmp','shm'):(self.state/n).mkdir()
        assert (self.state/'app/INSTRUCTION.md').is_file()
        assert docker('image','inspect',row['image'],'--format','{{.Id}}').stdout.strip()==row['image_id']
        # Docker does not support --ulimit as. A HARD cap set before spawning
        # the command is inherited by every command descendant.
        self.driver=('import resource; resource.setrlimit(resource.RLIMIT_AS, '
                     '(3221225472,3221225472))\n'+(ROOT/'command_driver.py').read_text())
        self._start()

    def _start(self):
        name='small-baseline-'+uuid.uuid4().hex[:16]
        save(self.directory/'container.json',{'name':name,'job':self.directory.name})
        args=['run','-d','--init','--name',name,'--label','experiment='+ROOT.name,'--label','job='+self.directory.name,
            '--user',f'{os.getuid()}:{os.getgid()}','--cpus','2','--memory','8g','--pids-limit','128',
            '--read-only','--cap-drop','ALL',
            '--security-opt','no-new-privileges','--network','none']
        for src,dst in [('app','/app'),('home','/baseline-home'),('tmp','/tmp'),('shm','/dev/shm')]:
            args+=['--mount',f'type=bind,src={self.state/src},dst={dst}']
        args+=['--mount',f'type=bind,src={ROOT/"empty-tests"},dst=/tests,readonly',
            '-e','HOME=/baseline-home','-e','BASH_ENV=/dev/null','-e','ENV=/dev/null','-w','/app',
            self.row['image_id'],'sleep','infinity']
        docker(*args,seconds=45)
        self.current=name
        x=json.loads(docker('inspect',name).stdout)[0]
        assert x['HostConfig']['ReadonlyRootfs'] and x['HostConfig']['NetworkMode']=='none'
        assert x['HostConfig']['Init'] is True
        assert x['HostConfig']['Memory']==8*2**30 and x['HostConfig']['NanoCpus']==2*10**9
        assert all(Path(m['Source']).is_relative_to(self.directory) for m in x['Mounts'] if m['RW'])
        save(self.directory/'isolation.json',{'network':'none','read_only_root':True,
            'cpu':2,'memory_gib':8,'process_address_space_gib':3,'all_write_mounts_snapshotted':True})

    def checkpoint(self,label):
        self.health(snapshot_started=time.time())
        archive=self.directory/'checkpoints'/(uuid.uuid4().hex+'.tar.gz')
        archive.parent.mkdir(exist_ok=True)
        artifact=export_tree(self.state,archive)
        record={'path':str(archive),'sha256':artifact['sha256'],'label':label}
        self.records[str(archive)]=record
        self.health(snapshot_finished=time.time(),checkpoints=len(self.records))
        return record

    def restore(self,record):
        self.health(restore_started=time.time())
        assert self.records.get(record['path'])==record and sha(record['path'])==record['sha256']
        close_owned(self.directory);self.current=None
        stage=self.directory/('restore-'+uuid.uuid4().hex)
        import_tree(record['path'],stage)
        # Exact per-job paths, no broad recursive deletion. Old live state is retired
        # until restoration succeeds, then released to bound storage.
        retired=self.directory/('retired-'+uuid.uuid4().hex)
        self.state.rename(retired);stage.rename(self.state)
        self._start()
        assert retired.parent.resolve()==self.directory.resolve()
        shutil.rmtree(retired)
        self.health(restore_finished=time.time())

    def execute(self,action):
        if self.tools>=600:raise BudgetStop('tool_calls')
        remaining=self.deadline-time.monotonic()
        if remaining<=0:raise BudgetStop('wall_seconds')
        argv=action.get('argv')
        if not isinstance(argv,list) or not argv or any(not isinstance(s,str) for s in argv):
            raise ValueError('invalid_argv')
        if sum(len(s) for s in argv)>24000:raise ValueError('argv_capacity')
        cwd=action.get('cwd','.')
        from posixpath import normpath,join
        cwd=normpath(join('/app',cwd))
        if cwd!='/app' and not cwd.startswith('/app/'):raise ValueError('invalid_cwd')
        duration=action.get('timeout_seconds',300)
        if isinstance(duration,bool) or not isinstance(duration,(int,float)) or not 0<duration<=300:
            raise ValueError('invalid_duration')
        stdin=action.get('stdin') or ''
        if not isinstance(stdin,str) or len(stdin)>24000:raise ValueError('stdin_capacity')
        self.tools+=1;self.health(tool_calls=self.tools,tool_started=time.time())
        body={'argv':argv,'cwd':cwd,'stdin':stdin,'seconds':min(duration,remaining), 'output_limit':1024*1024}
        p=docker('exec','-i',self.current,'python3','-c',self.driver,
                 input=json.dumps(body),seconds=body['seconds']+15)
        result=json.loads(p.stdout)
        save(self.directory/'tools'/f'{self.tools:04d}.json',{'action':action,'result':result})
        self.health(tool_calls=self.tools,tool_finished=time.time())
        return result

    def close(self):close_owned(self.directory);self.current=None

    def export(self):
        return export_tree(self.state/'app',self.directory/'final-source.tar.gz',source_only=True)
