"""Model-free sequential grading with final rescan; no per-artifact retries."""
import json
from pathlib import Path
import shutil
import subprocess
import os
import signal
import sys
import time
from common import ROOT,save,sha


def eligible():
    records={}
    for d in sorted((ROOT/'jobs').glob('retrac--*')):
        if not (d/'summary.json').exists():continue
        summary=json.loads((d/'summary.json').read_text())
        if summary.get('state')=='awaiting_grade':records[d.name]=(d,summary)
    return records


def dispatch(job,source,summary):
    # grade_one owns the shared advisory lock; unrelated containers cannot block us.
    dest=ROOT/'incoming'/job
    assert sha(source/'final-source.tar.gz')==summary['artifact']['sha256']
    if not dest.exists():
        dest.mkdir(parents=True);shutil.copyfile(source/'final-source.tar.gz',dest/'final-source.tar.gz')
        save(dest/'summary.json',summary)
    else:
        assert sha(dest/'final-source.tar.gz')==summary['artifact']['sha256']
        assert not (dest/'grading.claim').exists(),'Existing grading claim: inspect; never retry'
    with (dest/'grading-worker.log').open('x') as out,(dest/'grading-stderr.log').open('x') as err:
        process=subprocess.Popen([sys.executable,'-B',str(ROOT/'grade_one.py'),'--job',job],
            stdin=subprocess.DEVNULL,stdout=out,stderr=err,start_new_session=True)
        started=time.monotonic()
        while process.poll() is None:
            save(ROOT/'grading-health.json',{'state':'grading','current_job':job,'updated':time.time(),
                 'scored':len(list((ROOT/'grades').glob('*/result.json'))),'errors':{},'model_calls':0})
            if time.monotonic()-started>1800:
                os.killpg(process.pid,signal.SIGKILL)
                process.wait(timeout=5)
                raise TimeoutError('official_grading_worker_deadline')
            time.sleep(10)
        result=process
    report=ROOT/'grades'/job/'result.json'
    if not report.exists() or json.loads(report.read_text()).get('grading_state')!='complete':
        raise RuntimeError('grading_failed_inspect_no_retry')
    receipt=json.loads(report.read_text())
    if result.returncode or receipt.get('grading_cleanup_error') or receipt.get('grading_cleanup_errors'):
        raise RuntimeError('official_score_saved_but_cleanup_failed')


def main(dispatcher=None):
    dispatcher=dispatcher or dispatch;errors={}
    while True:
        for job,(source,summary) in eligible().items():
            report=ROOT/'grades'/job/'result.json'
            if report.exists() or job in errors:continue
            try:dispatcher(job,source,summary)
            except Exception as error:
                errors[job]=str(error)[:200]
                break  # No next grader on a broken Docker control plane.
        hpath=ROOT/'health.json';h=json.loads(hpath.read_text()) if hpath.exists() else {}
        # Rescan AFTER reading terminal controller state: never exit on an old list.
        available=eligible()
        reports={p.parent.name:json.loads(p.read_text()) for p in (ROOT/'grades').glob('*/result.json')}
        complete={job for job,r in reports.items() if r.get('grading_state')=='complete'}
        for job,r in reports.items():
            if r.get('grading_state')!='complete':errors[job]='existing_failed_grading_requires_explicit_repair'
        missing=set(available)-complete-set(errors)
        terminal=h.get('state') in ('generation_complete','needs_attention') and not h.get('active')
        state='needs_attention' if errors else ('grading' if missing or not terminal else 'complete_for_available_artifacts')
        save(ROOT/'grading-health.json',{'updated':time.time(),'state':state,'scored':len(complete),
            'available':len(available),'missing':sorted(missing),'errors':errors,'model_calls':0})
        if errors or (terminal and not missing):
            if not errors and terminal:
                from full20_results import build
                build()
            break
        time.sleep(2 if terminal else 15)

if __name__=='__main__':main()
