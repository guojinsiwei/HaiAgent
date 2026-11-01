"""Explicitly authorized regrading of the SAME frozen DH artifact. No model."""
import json
from pathlib import Path
import time

from common import ROOT,save
from relay import college,command,KEY,REMOTE,COLLEGE,GRADER_PY

JOB='roundtrip--61810_pgtbl'
ORIGINAL='dh--61810_pgtbl'

def main():
    original=json.loads((ROOT/'official-score-return'/ORIGINAL/'official-report.json').read_text())
    expected=original['artifact_sha256']
    assert original['grading_state']=='failed' and original['script_exit']==124
    marker=ROOT/'grading-retry-dh-pgtbl.json'
    record=dict(job=JOB,method='dh',retry_of=ORIGINAL,artifact_sha256=expected,attempt=2,
        model_calls=0,solving_repeated=False,official_script_unchanged=True,timeout_seconds=300,
        grading_cpu=8,grading_memory_gib=8,original_preserved=True,created=time.time())
    existing=college('test ! -f '+COLLEGE+'/grades/'+JOB+'/result.json || cat '+COLLEGE+'/grades/'+JOB+'/result.json')
    if not existing:
        claim=college('test ! -d '+COLLEGE+'/grades/'+JOB+' || echo exists').strip()
        assert not claim,'Supplementary grading already claimed; never replay automatically'
        college('cd '+COLLEGE+' && '+GRADER_PY+' -B validate_college.py')
        save(marker,dict(record,state='grading'))
        try:
            college('cd '+COLLEGE+' && '+GRADER_PY+' -B college_grader.py --job '+JOB+
                ' --archive incoming-'+ORIGINAL+'.tar.gz --sha256 '+expected,seconds=420,
                retry_safe=False,stage='User-approved DH pgtbl regrading')
        except RuntimeError:
            pass
        existing=college('test ! -f '+COLLEGE+'/grades/'+JOB+'/result.json || cat '+COLLEGE+'/grades/'+JOB+'/result.json')
        if not existing:
            save(marker,dict(record,state='claimed_result_unknown',updated=time.time()))
            raise RuntimeError('No final grading report yet; claimed work will not replay')
    result=json.loads(existing)
    assert result['artifact_sha256']==expected and result['fixture'] is False
    output=ROOT/'grading-retry'/ORIGINAL;output.mkdir(parents=True,exist_ok=True)
    save(output/'official-report.json',result)
    command(['scp','-i',KEY,'-o','BatchMode=yes','-o','ConnectTimeout=15',
        REMOTE+':'+COLLEGE+'/grades/'+JOB+'/console.log',str(output/'grading-console.log')])
    if college('test ! -d '+COLLEGE+'/grades/'+JOB+'/test_output || echo exists').strip():
        command(['scp','-r','-i',KEY,'-o','BatchMode=yes','-o','ConnectTimeout=15',
            REMOTE+':'+COLLEGE+'/grades/'+JOB+'/test_output',str(output)])
    save(marker,dict(record,state='complete' if result['grading_state']=='complete' else 'failed',
        updated=time.time(),result=result))
    print(json.dumps(dict(state=result['grading_state'],job=JOB,script_exit=result['script_exit'],
        f2p=result.get('f2p'),error=result.get('error'),model_calls=0)),flush=True)

if __name__=='__main__':main()
