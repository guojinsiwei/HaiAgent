"""Freeze once, grade once; no score is passed to a solver or retry policy."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
from common import ROOT,save,sha
from resume_worker import read,valid


def main():
    plan=read(ROOT/'resume-plan.json');method=plan['method'];errors=[];completed=[]
    while True:
        for row in plan['run_tasks']:
            job=method+'--'+row['task'];d=ROOT/'jobs'/job
            report=ROOT/'grades'/job/'result.json'
            if job in completed or any(e['job']==job for e in errors):continue
            if report.exists():
                r=read(report)
                if r.get('grading_state')=='complete':completed.append(job)
                else:errors.append({'job':job,'reason':'grading_failed'})
                continue
            summary=read(d/'summary.json')
            if not valid(summary):continue
            target=ROOT/'incoming'/job
            if not target.exists():
                target.mkdir(parents=True)
                shutil.copyfile(d/'final-source.tar.gz',target/'final-source.tar.gz')
                save(target/'summary.json',summary)
            assert sha(target/'final-source.tar.gz')==summary['artifact']['sha256']
            if (target/'grading.claim').exists():
                errors.append({'job':job,'reason':'claimed_without_report'});continue
            save(ROOT/'grading-health.json',{'state':'grading','job':job,'completed':completed,
                'errors':errors,'updated':time.time(),'model_calls':0})
            with (target/'resume-grade.log').open('x') as out:
                result=subprocess.run([sys.executable,'-B',str(ROOT/'grade_one.py'),'--job',job],
                    stdin=subprocess.DEVNULL,stdout=out,stderr=subprocess.STDOUT)
            r=read(report)
            if result.returncode or r.get('grading_state')!='complete' or not r.get('grading_container_destroyed'):
                errors.append({'job':job,'reason':'grading_or_cleanup_failed'})
            else:completed.append(job)
        h=read(ROOT/'health.json')
        terminal=h.get('state') in ('generation_complete','needs_attention') and not h.get('active')
        # A new artifact can arrive during the scan; require a final complete rescan.
        missing=[r for r in plan['run_tasks'] if valid(read(ROOT/'jobs'/(method+'--'+r['task'])/'summary.json'))
            and method+'--'+r['task'] not in completed and not any(e['job']==method+'--'+r['task'] for e in errors)]
        save(ROOT/'grading-health.json',{'state':'needs_attention' if errors else
            ('complete_for_available_artifacts' if terminal and not missing else 'waiting'),
            'completed':completed,'preserved':len(plan['preserved']),'errors':errors,
            'updated':time.time(),'model_calls':0})
        if terminal and not missing:return
        time.sleep(5)

if __name__=='__main__':main()
