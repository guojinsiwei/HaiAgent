"""College-side evaluator clock repair for one frozen pgtbl artifact only.

The official pgtbl suite includes two 300-second QEMU tests plus other tests.
Allow its existing internal limits to finish and emit an actual Score line;
never edit official tests, source, limits inside tests, or the sealed protocol.
"""
import json
from pathlib import Path
import re
import sys

from common import ROOT,save
import validate_college
import college_grader as grader

ORIGINAL='dh--61810_pgtbl'
JOB='roundtrip--outer-clock-fix--61810_pgtbl'
TIMEOUT=900

def repair_run(original_run):
    def run(argv,*args,**kwargs):
        argv=list(argv)
        if len(argv)==7 and argv[:2]==['docker','exec'] and argv[3]=='timeout' and argv[5:] == ['bash','/tests/run-tests.sh']:
            assert argv[4]=='300','Unexpected official suite outer clock'
            argv[4]=str(TIMEOUT)
            assert kwargs['timeout']==360
            kwargs['timeout']=TIMEOUT+60
        return original_run(argv,*args,**kwargs)
    return run

def main():
    validate_college.main()
    failed=json.loads((ROOT/'grades'/ORIGINAL/'result.json').read_text())
    assert failed['script_exit']==124 and failed['grading_state']=='failed'
    # Narrow monkeypatch affects only the external timeout around this suite;
    # original grader integrity checks and all official parser logic still run.
    original_run=grader.subprocess.run
    grader.subprocess.run=repair_run(original_run)
    try:
        result=grader.grade(JOB,ROOT/('incoming-'+ORIGINAL+'.tar.gz'),failed['artifact_sha256'])
    finally:grader.subprocess.run=original_run
    result.update(regrade_of=ORIGINAL,outer_clock_original=300,outer_clock_repaired=TIMEOUT,
        official_internal_test_limits_unchanged=True,model_calls=0,source_edits=0)
    if result['grading_state']=='complete':
        output=(ROOT/'grades'/JOB/'test_output/f2p_output.txt').read_text(errors='replace')
        match=re.search(r'Score:\s*(\d+)\s*/\s*(\d+)',output)
        assert match,'No completed official Score line; cannot call it a valid completed suite'
        result['official_score_line']=match.group(0)
    save(ROOT/'grades'/JOB/'result.json',result)
    print(json.dumps(result),flush=True)

if __name__=='__main__':main()
