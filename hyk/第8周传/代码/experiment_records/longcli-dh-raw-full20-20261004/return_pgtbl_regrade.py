"""No-model result return for the explicitly authorized outer-clock repair."""
import json
import os
import time

from common import ROOT,save
from relay import college,command,KEY,REMOTE,COLLEGE,RelayNetworkError
from build_report import build
from pull_official_scores import pull

JOB='roundtrip--outer-clock-fix--61810_pgtbl'
MARKER=ROOT/'grading-outer-clock-dh-pgtbl.json'

def main():
    import msvcrt
    lock=(ROOT/'pgtbl-score-return.lock').open('a+b')
    lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    save(ROOT/'pgtbl-score-return-process.json',dict(pid=os.getpid(),started=time.time(),model_calls=0))
    began=time.monotonic()
    while time.monotonic()-began<1800:
        try:
            content=college('test ! -f '+COLLEGE+'/grades/'+JOB+'/result.json || cat '+COLLEGE+'/grades/'+JOB+'/result.json')
            if content:
                result=json.loads(content)
                record=json.loads(MARKER.read_text())
                assert result['artifact_sha256']==record['artifact_sha256']
                # The sealed grader atomically publishes first; the wrapper then
                # adds provenance. Do not mistake that short window for a fault.
                if result.get('outer_clock_repaired')!=900:
                    time.sleep(2);continue
                assert result['fixture'] is False
                target=ROOT/'grading-retry/dh--61810_pgtbl/outer-clock-fix';target.mkdir(parents=True,exist_ok=True)
                save(target/'official-report.json',result)
                command(['scp','-i',KEY,'-o','BatchMode=yes','-o','ConnectTimeout=15',
                    REMOTE+':'+COLLEGE+'/grades/'+JOB+'/console.log',str(target/'grading-console.log')])
                command(['scp','-r','-i',KEY,'-o','BatchMode=yes','-o','ConnectTimeout=15',
                    REMOTE+':'+COLLEGE+'/grades/'+JOB+'/test_output',str(target)])
                pull();build()
                save(MARKER,dict(record,state=result['grading_state'],updated=time.time(),result=result))
                print(json.dumps(dict(state=result['grading_state'],f2p=result.get('f2p'),
                    p2p=result.get('p2p_step_score'),official_success=result.get('official_success'),model_calls=0)))
                return
        except RelayNetworkError as error:
            save(ROOT/'pgtbl-score-return-error.json',dict(state='network_unknown_retrying',message=str(error),updated=time.time()))
        time.sleep(15)
    save(ROOT/'pgtbl-score-return-error.json',dict(state='needs_attention',reason='No completed result after bounded return wait; do not replay grading',updated=time.time()))

if __name__=='__main__':main()
