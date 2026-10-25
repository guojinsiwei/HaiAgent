"""Isolated keyless handoff fixture only. Never import the experiment runner."""
import json,os,subprocess,sys,time
from pathlib import Path
def save(p,v):
    p.parent.mkdir(parents=True,exist_ok=True)
    temp=p.with_name(p.name+'.'+str(os.getpid())+'.tmp')
    temp.write_text(json.dumps(v));os.replace(temp,p)
def main():
    root=Path(sys.argv[1]);mode=sys.argv[2] if len(sys.argv)>2 else 'controller'
    if mode=='child':
        job=sys.argv[3];d=root/'jobs'/job;began=time.time()
        while time.time()-began<6:
            save(d/'health.json',dict(job=job,pid=os.getpid(),started=began,updated=time.time(),state='running'))
            time.sleep(.1)
        summary=dict(job=job,pid=os.getpid(),started=began,updated=time.time(),state='awaiting_grade',
                     fixture_only=True,paid_model_calls=0)
        save(d/'summary.json',summary);save(d/'health.json',summary);return
    if mode=='grader':
        while True:
            save(root/'grading-health.json',dict(state='grading',errors={},model_calls=0,updated=time.time()))
            if (root/'fixture-stop-grader').exists():return
            time.sleep(.1)
    jobs=['tools--pilot','plain--pilot']
    for job in jobs:subprocess.Popen([sys.executable,'-B',__file__,str(root),'child',job])
    grader=subprocess.Popen([sys.executable,'-B',__file__,str(root),'grader'])
    save(root/'grading-launch.json',dict(pid=grader.pid))
    while True:
        save(root/'health.json',dict(pid=os.getpid(),active=jobs,pending=[],completed=[],errors=[],fatal=None,updated=time.time()))
        time.sleep(.1)
if __name__=='__main__':main()
