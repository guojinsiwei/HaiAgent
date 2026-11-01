import json
from pathlib import Path
import shutil
from common import ROOT,sha,save
from safe_process import run_bounded

assert sha(ROOT/'college_grader.py')=='e557933f3896136ec32b0827e255b7f1b96027c56ec336de4403018425acd298'
import college_grader
import grading_adapter
import grade_one
plan=json.loads((ROOT/'resume-plan.json').read_text())
checks=[]
for row in plan['run_tasks']:
    p=run_bounded(['docker','image','inspect',row['image'],'--format','{{.Id}}'],
        timeout=15,capture_output=True,text=True)
    assert p.returncode==0 and p.stdout.strip()==row['image_id'],row['task']
    checks.append({'task':row['task'],'image_id':row['image_id']})
for r in plan['preserved']:assert sha(Path(r['report']))==r['report_sha256']
p=ROOT/'host-tmp'/'write-probe';p.write_bytes(b'verified');assert p.read_bytes()==b'verified';p.unlink()
save(ROOT/'grading-ready.json',{'ready':True,'paid_model_calls':0,'checks':checks,
    'preserved':len(plan['preserved']),'free_bytes':shutil.disk_usage(ROOT).free,
    'grader_sha256':sha(ROOT/'college_grader.py')})
print(json.dumps({'grading_ready':True,'tasks':len(checks),'preserved':len(plan['preserved']),'model_calls':0}))
