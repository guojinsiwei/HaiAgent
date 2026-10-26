"""Laptop-side result relay. Only public artifacts, never controller credentials."""
import json
import os
from pathlib import Path
import subprocess
import time
from common import ROOT,sha,save

CUBE='/mnt/lizh639/longcli-v6-raw-paired10-20261001'
COLLEGE='/var/tmp/lizh639-longcli-v6-raw-paired10-20261001'
REMOTE='lizh639@172.16.108.236'
KEY=str(Path.home()/'.ssh/cubestudio_notebook')
GRADER_PY='/mnt/sdb/home/lizh639/terminalbench-v14-setup/runtime/bin/python'

def command(argv,seconds=120):
    p=subprocess.run(argv,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=seconds)
    if p.returncode: raise RuntimeError('Relay command failed (see relay.log); no automatic grade replay')
    return p.stdout

def college(cmd,seconds=120):
    return command(['ssh','-i',KEY,'-o','BatchMode=yes',REMOTE,cmd],seconds)

def main():
    incoming=ROOT/'received'; incoming.mkdir(exist_ok=True)
    protocol=json.loads((ROOT/'protocol.json').read_text())
    expected=[method+'--'+row['task'] for row in protocol['tasks'] for method in protocol['methods']]
    done={p.parent.name:json.loads(p.read_text()) for p in incoming.glob('*/grade.json')}
    while len(done)<20:
        healths=[]
        for worker in (0,1):
            host='cubestudio_container' if worker==0 else 'cubestudio_container2'
            content=command(['ssh','-o','BatchMode=yes',host,
                'test ! -f '+CUBE+'/health-'+str(worker)+'.json || cat '+CUBE+'/health-'+str(worker)+'.json'])
            if content: healths.append(json.loads(content))
        for health in healths:
            for summary in health.get('results',[]):
                job=summary['job']
                assert job in expected
                if job in done: continue
                target=incoming/job; target.mkdir(exist_ok=True)
                # Recover an already scored artifact after relay interruption; never rerun its test.
                existing=college('test ! -f '+COLLEGE+'/grades/'+job+'/result.json || cat '+COLLEGE+'/grades/'+job+'/result.json')
                if existing:
                    result=json.loads(existing)
                    assert result['artifact_sha256']==summary['artifact']['sha256']
                else:
                    grading_dir=college('test ! -d '+COLLEGE+'/grades/'+job+' || echo exists').strip()
                    if grading_dir:
                        raise RuntimeError('Grading was already claimed but has no result: inspect remote state; never replay automatically')
                    remote_archive=CUBE+'/runs/'+job+'/source.tar.gz'
                    command(['scp','-o','BatchMode=yes','cubestudio_container:'+remote_archive,str(target/'source.tar.gz')],600)
                    assert sha(target/'source.tar.gz')==summary['artifact']['sha256']
                    command(['scp','-i',KEY,'-o','BatchMode=yes',str(target/'source.tar.gz'),REMOTE+':'+COLLEGE+'/incoming-'+job+'.tar.gz'],600)
                    try:
                        college('cd '+COLLEGE+' && '+GRADER_PY+' -B college_grader.py --job '+job+
                            ' --archive incoming-'+job+'.tar.gz --sha256 '+summary['artifact']['sha256'],1900)
                    except RuntimeError:
                        # A grading failure is a recorded infrastructure outcome, never silently zero.
                        pass
                    result=json.loads(college('cat '+COLLEGE+'/grades/'+job+'/result.json'))
                # Pull independent grader evidence and full generation logs; never checkpoints/key.
                for filename in ('model-audit.jsonl','result.json'):
                    command(['scp','-o','BatchMode=yes','cubestudio_container:'+CUBE+'/runs/'+job+'/'+filename,str(target/filename)],120)
                command(['scp','-r','-o','BatchMode=yes','cubestudio_container:'+CUBE+'/runs/'+job+'/trace',str(target)],300)
                test_output=college('test ! -d '+COLLEGE+'/grades/'+job+'/test_output || echo exists').strip()
                if test_output:
                    command(['scp','-r','-i',KEY,'-o','BatchMode=yes',REMOTE+':'+COLLEGE+'/grades/'+job+'/test_output',str(target)],120)
                command(['scp','-i',KEY,'-o','BatchMode=yes',REMOTE+':'+COLLEGE+'/grades/'+job+'/console.log',str(target/'grading-console.log')],120)
                save(target/'generation-summary.json',summary)
                save(target/'grade.json',result)
                done[job]=result
        arms={method:dict(generated=sum(r['method']==method for h in healths for r in h.get('results',[])),
             graded=sum(job.startswith(method+'--') for job in done),
             grading_failures=sum(job.startswith(method+'--') and r['grading_state']!='complete' for job,r in done.items()),
             official_successes=sum(job.startswith(method+'--') and r.get('official_success') is True for job,r in done.items()),
             f2p_scores={r['task']:r.get('f2p',{}).get('step_score') for job,r in done.items() if job.startswith(method+'--')})
             for method in protocol['methods']}
        report=dict(generated=sum(h.get('completed',0) for h in healths),graded=len(done),total=20,arms=arms,
                    workers=healths,results=done,updated=time.time())
        save(ROOT/'paired-status.json',report)
        if healths and all(h['state'] in ('completed','failed') for h in healths) and len(healths)==2:
            # Both workers are terminal; remaining trials may be unstarted, not failures or zeroes.
            report['state']='complete' if len(done)==20 else 'incomplete'
            save(ROOT/'paired-status.json',report); break
        time.sleep(60)

if __name__=='__main__':
    try: main()
    except Exception as error:
        save(ROOT/'relay-error.json',dict(error_type=type(error).__name__,message=str(error),time=time.time()))
        raise
