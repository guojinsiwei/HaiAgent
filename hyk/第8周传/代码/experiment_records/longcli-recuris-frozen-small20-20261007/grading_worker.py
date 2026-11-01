"""Serial official grading, no model calls and no automatic regrade."""
import json
import subprocess
import sys
import time
from common import ROOT,save
from grade_one import valid_jobs

def main():
    jobs=valid_jobs();completed=[];errors=[]
    while True:
        for job in sorted(jobs):
            result=ROOT/'grades'/job/'result.json'
            if result.exists():
                r=json.loads(result.read_text())
                if r.get('grading_state')!='complete' or not r.get('grading_container_destroyed'):
                    errors.append({'job':job,'reason':'grading_or_cleanup_failed'})
                if job not in completed:completed.append(job)
                continue
            if not (ROOT/'incoming'/job/'summary.json').exists():continue
            if (ROOT/'incoming'/job/'grading.claim').exists():
                errors.append({'job':job,'reason':'claimed_without_result'});break
            save(ROOT/'grading-health.json',{'state':'grading','job':job,'completed':completed,
                'updated':time.time(),'errors':errors,'model_calls':0})
            # Official per-task command timeout is enforced inside the single-job grader.
            p=subprocess.run([sys.executable,'-B',str(ROOT/'grade_one.py'),'--job',job])
            if p.returncode or not result.exists():errors.append({'job':job,'reason':'grader_process_failed'})
            else:
                r=json.loads(result.read_text())
                if r.get('grading_state')!='complete' or not r.get('grading_container_destroyed'):
                    errors.append({'job':job,'reason':'grading_or_cleanup_failed'})
                else:completed.append(job)
            if errors:break
        controller=ROOT/'health.json'
        stopped=controller.exists() and json.loads(controller.read_text()).get('state')=='needs_attention'
        state='needs_attention' if errors else ('complete' if len(completed)==len(jobs) else 'waiting')
        save(ROOT/'grading-health.json',{'state':state,'completed':completed,'errors':errors,
                                        'updated':time.time(),'model_calls':0})
        if errors or len(completed)==len(jobs) or stopped:return
        time.sleep(5)

if __name__=='__main__':main()
