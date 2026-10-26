"""Quiesce four owned dead attempts; snapshot before removing Docker volumes."""
import json
from pathlib import Path
import time
from common import ROOT,save
from docker_terminal import docker
import docker_cleanup

OLD=Path('/var/tmp/lizh639-longcli-retrac-recovery3-20261007')
TASKS=('61810_cow','61810_fs','61810_lock','61810_mmap')

def main():
    results=[]
    for task in TASKS:
        directory=OLD/'jobs'/('retrac--'+task)
        info=json.loads((directory/'container.json').read_text())
        assert info['job']=='retrac--'+task and info['experiment']==OLD.name
        target=ROOT/'interrupted-workspaces'/task
        inspected=docker('inspect',info['name'],'--format','{{json .Config.Labels}}',check=False,seconds=8)
        if inspected.returncode:
            assert target.exists() and any(target.iterdir()),'Missing original and snapshot'
            result={'task':task,'snapshot':str(target),'state':'previously_preserved'}
        else:
            labels=json.loads(inspected.stdout)
            assert labels.get('experiment')==OLD.name and labels.get('job')==info['job']
            state=json.loads(docker('inspect',info['name'],'--format','{{json .State}}',seconds=8).stdout)
            assert not state['OOMKilled']
            docker_cleanup.ROOT=OLD
            receipt=docker_cleanup.cleanup(docker,info['name'],info['job'],target)
            assert receipt['state']=='snapshot_retained_container_removed'
            assert Path(receipt['snapshot']).is_dir() and any(Path(receipt['snapshot']).iterdir())
            result={'task':task,'snapshot':receipt['snapshot'],'state':receipt['state'],
                    'original_exit_code':state['ExitCode'],'original_oom_killed':state['OOMKilled']}
        results.append(result)
        save(ROOT/'interrupted-workspaces'/'rescue-progress.json',{'updated':time.time(),'results':results,
            'paid_model_calls':0,'original_logs_retained':True})
        print(json.dumps(result),flush=True)
    save(ROOT/'interrupted-workspaces'/'rescue-complete.json',{'state':'passed','results':results,
         'old_workspaces_preserved':4,'paid_model_calls':0,'time':time.time()})

if __name__=='__main__':main()
