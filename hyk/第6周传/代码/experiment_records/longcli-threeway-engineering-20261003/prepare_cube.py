"""Fresh no-model solver acceptance on the existing two CubeStudio hosts."""
import json
import os
from pathlib import Path
import subprocess
import sys
from common import ROOT,PYTHON,save,sha

OLD=Path('/mnt/lizh639/longcli-v6-raw-paired10-20261001')
def main(worker):
    p=json.loads((ROOT/'protocol.json').read_text())
    if (ROOT/'claims').exists() or (ROOT/('health-'+str(worker)+'.json')).exists():raise RuntimeError('Never reprepare live experiment')
    if worker==0:
        (ROOT/'templates').symlink_to(OLD/'templates',target_is_directory=True)
        for family,info in p['base_images'].items():
            if sha(OLD/info['archive'])!=info['sha256']:raise RuntimeError('Original template archive changed')
            (ROOT/info['archive']).symlink_to(OLD/info['archive'])
            save(ROOT/('template-'+family+'.json'),dict(rootfs_sha256=info['sha256'],complete=True))
    for method in p['methods']:
        arm=ROOT/'arms'/('v8' if method=='orthogonal-v8' else 'v6')
        env=dict(os.environ,LONGCLI_METHOD=method,PYTHONDONTWRITEBYTECODE='1',
                 PYTHONPATH=os.pathsep.join(map(str,[arm/'bestfgs-project/src',arm/'hai-project/src',ROOT])))
        logfile=ROOT/f'wire-regression-{worker}-{method}.log'
        with logfile.open('x') as stream:
            subprocess.run([PYTHON,'-B','-m','unittest','test_shared_wire','test_deployment'],cwd=ROOT,env=env,
                           stdout=stream,stderr=subprocess.STDOUT,check=True,timeout=120)
    with (ROOT/f'solver-preflight-{worker}.log').open('x') as stream:
        subprocess.run([PYTHON,'-B',str(ROOT/'cube_prepare.py'),'--worker',str(worker)],cwd=ROOT,
                       stdout=stream,stderr=subprocess.STDOUT,check=True,timeout=3600)
    print(json.dumps(dict(worker=worker,passed=True,model_calls=0)))

if __name__=='__main__':main(int(sys.argv[1]))
