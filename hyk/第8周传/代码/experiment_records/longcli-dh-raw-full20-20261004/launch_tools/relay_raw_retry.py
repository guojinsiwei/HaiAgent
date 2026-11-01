"""Model-free supplementary result relay; never merges away original failure."""
import json
import os
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from common import save,sha
from relay import cube_ssh,cube_scp,college,command,CUBE,COLLEGE,KEY,REMOTE,GRADER_PY,WORKERS,PROXY,RelayNetworkError

JOB='roundtrip--cs61_fa24_scheme'
TARGET=ROOT/'network-retry/raw--cs61_fa24_scheme'
STATUS=ROOT/'raw-scheme-retry-status.json'

def record(state,**fields):
    save(STATUS,dict(state=state,job=JOB,method='raw',attempt=2,retry_of='raw--cs61_fa24_scheme',
        original_retained=True,updated=time.time(),**fields))

def collect():
    TARGET.mkdir(parents=True,exist_ok=True)
    summary_text=cube_ssh(1,'test ! -f '+CUBE+'/launch_tools/raw-scheme-retry-summary.json || cat '+CUBE+'/launch_tools/raw-scheme-retry-summary.json')
    if not summary_text:
        error=cube_ssh(1,'test ! -f '+CUBE+'/launch_tools/raw-scheme-retry-error.json || cat '+CUBE+'/launch_tools/raw-scheme-retry-error.json')
        if error:
            record('generation_infrastructure_error',error=json.loads(error));return True
        record('running');return False
    summary=json.loads(summary_text)
    save(TARGET/'generation-summary.json',summary)
    result_text=college('test ! -f '+COLLEGE+'/grades/'+JOB+'/result.json || cat '+COLLEGE+'/grades/'+JOB+'/result.json')
    if not result_text:
        claim=college('test ! -d '+COLLEGE+'/grades/'+JOB+' || echo exists').strip()
        if claim:
            record('grading_claimed_waiting',generation=summary);return False
        cube_scp(CUBE+'/runs/'+JOB+'/source.tar.gz',TARGET/'source.tar.gz',600)
        assert sha(TARGET/'source.tar.gz')==summary['artifact']['sha256']
        command(['scp','-i',KEY,'-o','BatchMode=yes','-o','ConnectTimeout=15',str(TARGET/'source.tar.gz'),
            REMOTE+':'+COLLEGE+'/incoming-'+JOB+'.tar.gz'],600)
        college('cd '+COLLEGE+' && '+GRADER_PY+' -B validate_college.py')
        record('grading',generation=summary)
        try:
            college('cd '+COLLEGE+' && '+GRADER_PY+' -B college_grader.py --job '+JOB+
                ' --archive incoming-'+JOB+'.tar.gz --sha256 '+summary['artifact']['sha256'],1900,
                retry_safe=False,stage='Supplementary RAW official grading')
        except RuntimeError:
            pass  # Preserve claim; never resubmit an uncertain grading operation.
        result_text=college('test ! -f '+COLLEGE+'/grades/'+JOB+'/result.json || cat '+COLLEGE+'/grades/'+JOB+'/result.json')
        if not result_text:record('grading_claimed_waiting',generation=summary);return False
    result=json.loads(result_text)
    assert result['artifact_sha256']==summary['artifact']['sha256'] and not result['fixture']
    for filename in ('model-audit.jsonl','result.json'):
        cube_scp(CUBE+'/runs/'+JOB+'/'+filename,TARGET/filename,300)
    remote,port=WORKERS[0]
    command(['scp','-r','-i',KEY,'-P',port,'-o','BatchMode=yes','-o',PROXY,
        remote+':'+CUBE+'/runs/'+JOB+'/trace',str(TARGET)],300)
    if college('test ! -d '+COLLEGE+'/grades/'+JOB+'/test_output || echo exists').strip():
        command(['scp','-r','-i',KEY,'-o','BatchMode=yes',REMOTE+':'+COLLEGE+'/grades/'+JOB+'/test_output',str(TARGET)],300)
    command(['scp','-i',KEY,'-o','BatchMode=yes',REMOTE+':'+COLLEGE+'/grades/'+JOB+'/console.log',str(TARGET/'grading-console.log')],120)
    save(TARGET/'grade.json',result)
    record('complete' if result['grading_state']=='complete' else 'grading_failed',generation=summary,grade=result)
    return True

if __name__=='__main__':
    import msvcrt
    lock=(ROOT/'raw-scheme-retry-relay.lock').open('a+b')
    lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    save(ROOT/'raw-scheme-retry-relay-process.json',dict(pid=os.getpid(),started=time.time(),model_calls=0))
    while True:
        try:
            if collect():break
        except RelayNetworkError as error:
            record('network_unknown_retrying',error=str(error))
        except Exception as error:
            record('needs_attention',error_type=type(error).__name__,error=str(error)[:500]);raise
        time.sleep(60)
