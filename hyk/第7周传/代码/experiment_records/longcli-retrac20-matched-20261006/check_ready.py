import argparse
import json
from common import ROOT,sha

def check(worker):
    ready=json.loads((ROOT/f'ready-{worker}.json').read_text())
    assert ready['ready'] and ready['worker']==worker and ready['paid_api_requests']==0
    for name,digest in ready['hashes'].items():assert sha(ROOT/name)==digest,'Sealed input changed: '+name
    receipt=json.loads((ROOT/ready['acceptance_file']).read_text())
    assert receipt['state']=='passed'
    assert all(r['state']=='keyless_pass' and r['task_processes_stopped'] and r['rounds']==8
        and r['recursive_memory_verified'] and r['persistent_terminal_verified']
        and r['maximum_input_bytes']<=48000 for r in receipt['trials'])
    offline=json.loads((ROOT/'original-tests.json').read_text())
    assert offline['exitcode']==0 and offline['summary']['failed']==0
    assert json.loads((ROOT/'adapter-tests.json').read_text())['passed']
    return True

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--worker',type=int,required=True);a=p.parse_args();check(a.worker)
    print(json.dumps({'state':'accepted','worker':a.worker,'paid_api_requests':0}))
