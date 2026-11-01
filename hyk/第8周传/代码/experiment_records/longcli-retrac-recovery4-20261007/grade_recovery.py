"""Score only the eleventh frozen historic artifact, using the official grader."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from common import ROOT,save,sha

def main():
    job='retrac--cmu15_445_p0';directory=ROOT/'incoming'/job
    summary=json.loads((directory/'summary.json').read_text())
    assert summary['artifact']['sha256']==sha(directory/'final-source.tar.gz')
    report=ROOT/'grades'/job/'result.json'
    if not report.exists():
        with (directory/'grading-worker.log').open('x') as out,(directory/'grading-stderr.log').open('x') as err:
            p=subprocess.run([sys.executable,'-B',str(ROOT/'grade_one.py'),'--job',job],
                stdin=subprocess.DEVNULL,stdout=out,stderr=err,timeout=1500)
        assert p.returncode==0,'Official grading failed; inspect receipt; never retry automatically'
    result=json.loads(report.read_text())
    assert result['grading_state']=='complete' and result['grading_container_destroyed']
    assert result['artifact_sha256']==summary['artifact']['sha256']
    save(ROOT/'grading-acceptance.json',{'state':'passed','paid_api_requests':0,'time':time.time(),
        'grade_only_job':job,'report':str(report),'artifact_sha256':result['artifact_sha256']})
    print(json.dumps({'state':'grade_only_complete','job':job,'f2p':result['f2p'],'paid_model_calls':0}))

if __name__=='__main__':main()
