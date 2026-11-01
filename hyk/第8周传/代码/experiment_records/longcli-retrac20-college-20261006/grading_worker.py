"""Model-free grading dispatcher; sequential, per-artifact claims, no retries."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
from common import ROOT,save,sha

def main():
    errors=[]
    while True:
        for d in sorted((ROOT/'jobs').glob('retrac--*')):
            s=d/'summary.json'
            if not s.exists():continue
            h=json.loads(s.read_text())
            if h.get('state')!='awaiting_grade':continue
            dest=ROOT/'incoming'/d.name
            if dest.exists():continue
            # Existing DSH official grading shares cores0-15. Do not contend
            # with an already-running official grader from another campaign.
            from docker_terminal import docker
            while docker('ps','--filter','name=longcli-paired10-','--format','{{.Names}}').stdout.strip():
                save(ROOT/'grading-health.json',{'updated':time.time(),'state':'waiting_for_existing_grader',
                    'job':d.name,'errors':errors,'model_calls':0})
                time.sleep(15)
            dest.mkdir()
            assert sha(d/'final-source.tar.gz')==h['artifact']['sha256']
            shutil.copyfile(d/'final-source.tar.gz',dest/'final-source.tar.gz');save(dest/'summary.json',h)
            with (dest/'grading-worker.log').open('x') as out,(dest/'grading-stderr.log').open('x') as err:
                result=subprocess.run([sys.executable,'-B',str(ROOT/'grade_one.py'),'--job',d.name],stdout=out,stderr=err)
            report=ROOT/'grades'/d.name/'result.json'
            if result.returncode or not report.exists() or json.loads(report.read_text()).get('grading_state')!='complete':
                errors.append({'job':d.name,'state':'grading_failed_inspect_no_retry'})
        hpath=ROOT/'health.json';h=json.loads(hpath.read_text()) if hpath.exists() else {}
        scored=list((ROOT/'grades').glob('*/result.json'))
        save(ROOT/'grading-health.json',{'updated':time.time(),'scored':len(scored),'errors':errors,'model_calls':0})
        if h.get('state') in ('generation_complete','needs_attention') and not h.get('active'):
            # Above pass consumes every final artifact before exiting.
            break
        time.sleep(15)

if __name__=='__main__':main()
