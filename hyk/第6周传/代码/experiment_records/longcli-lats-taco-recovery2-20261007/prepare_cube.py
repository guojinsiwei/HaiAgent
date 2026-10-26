import argparse
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import time
from common import ROOT,save,import_tree,sha

def own(root,uid):
    for parent,dirs,files in os.walk(root,followlinks=False):
        os.chown(parent,uid,uid,follow_symlinks=False)
        for name in dirs+files:os.chown(Path(parent)/name,uid,uid,follow_symlinks=False)

def main(worker):
    plan=json.loads((ROOT/'resume-plan.json').read_text());protocol=json.loads((ROOT/'protocol.json').read_text())
    rows=plan['run_tasks'][worker::2]
    plan.update(run_tasks=rows,concurrency=len(rows),root=str(ROOT),grading_backend='external_relay')
    protocol.update(tasks=rows,run_tasks=rows,total_trials=len(rows),concurrency=len(rows))
    for name in ('jobs','grades','incoming','host-tmp','empty-tests','acceptance-jobs'):(ROOT/name).mkdir(exist_ok=True)
    # Native setup once, BEFORE any model budgets start. No old task state copied.
    roots={};base=Path('/tmp/lizh639-taco-recovery2-20261007');base.mkdir(exist_ok=True)
    templates=Path('/mnt/lizh639/longcli-dh-raw-full20-20261004/templates')
    for slot,row in enumerate(rows):
        root=base/row['task'];uid=43000+worker*100+slot
        assert not root.exists(),'Do not overwrite an existing task root'
        root.mkdir()
        subprocess.run(['cp','-a','--reflink=auto',str(templates/row['family'])+'/.',str(root)],check=True,timeout=600)
        assert not (root/'tests').exists()
        if (root/'app').exists():
            assert not any((root/'app').iterdir()),'Template contains task data'
            (root/'app').rmdir()
        import_tree(ROOT/'starters'/('starter-'+row['task']+'.tar.gz'),root/'app')
        for name in ('app','tmp','baseline-home','dev/shm'):
            p=root/name;p.mkdir(parents=True,exist_ok=True);own(p,uid)
        dev=root/'dev';dev.mkdir(exist_ok=True)
        for name,minor in (('null',3),('zero',5),('random',8),('urandom',9)):
            p=dev/name
            if not p.exists():os.mknod(p,stat.S_IFCHR|0o666,os.makedev(1,minor))
            assert stat.S_ISCHR(p.lstat().st_mode);os.chmod(p,0o666)
        roots[row['task']]={'root':str(root),'uid':uid,'slot':slot}
        print(json.dumps({'prepared':row['task'],'model_calls':0}),flush=True)
    save(ROOT/'native-roots.json',roots);save(ROOT/'protocol.json',protocol);save(ROOT/'resume-plan.json',plan)
    shutil.copyfile(ROOT/'native_sandbox.py',ROOT/'sandbox.py')
    # Do not start a Docker grader on a machine that cannot run Docker.
    p=ROOT/'resume_worker.py';code=p.read_text()
    start=code.index("    with (ROOT/'grading-worker.log')")
    stop=code.index('    try:\n        while pending or active:',start)
    code=code[:start]+"    save(ROOT/'grading-launch.json',{'backend':'external_relay','model_calls':0})\n"+code[stop:]
    p.write_text(code)
    print(json.dumps({'prepared':True,'worker':worker,'tasks':len(rows),'concurrency':len(rows)}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--worker',type=int,required=True);main(p.parse_args().worker)
