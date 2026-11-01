"""Keyless official-grader lifecycle check, scores never exposed to paid solver."""
import json
import time
from pathlib import Path
from common import ROOT,save,sha
from docker_environment import BASE
from grading_adapter import install,cleanup_docker as docker
import college_grader

def main():
    cleanup=install(college_grader)
    archive=BASE/'starter-cs61_fa24_cats.tar.gz'
    job='roundtrip--cs61_fa24_cats'
    result=None
    try:
        result=college_grader.grade(job,archive,sha(archive),fixture=True)
    finally:
        for name in cleanup['owned']:
            p=docker('inspect',name,'--format','{{json .Config.Labels}}',check=False,seconds=10)
            if p.returncode and 'no such' in p.stderr.lower():continue
            assert p.returncode==0 and json.loads(p.stdout)['experiment']==ROOT.name
            if docker('inspect',name,'--format','{{.State.Running}}',seconds=10).stdout.strip()=='true':
                docker('kill',name,seconds=10)
            assert docker('inspect',name,'--format','{{.State.Running}}',seconds=10).stdout.strip()=='false'
            docker('rm',name,seconds=10)
    assert result and result['grading_state']=='complete',result
    assert not cleanup['errors'],cleanup
    save(ROOT/'grading-acceptance.json',{'state':'passed','paid_model_calls':0,'time':time.time(),
         'job':job,'official_report':str(ROOT/'fixture-grades'/job/'result.json'),
         'container_destroyed':True,'image_id':result['image_id']})
    print(json.dumps({'state':'passed','paid_model_calls':0,'official_grading_verified':True}))

if __name__=='__main__':main()
