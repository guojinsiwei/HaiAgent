"""Separate sequential official grader; scores never enter solver context."""
import json
import shutil
import subprocess
import sys
import time
from common import ROOT,save,sha

def eligible():
    for d in sorted((ROOT/'jobs').iterdir()):
        p=d/'summary.json'
        if not p.exists():continue
        s=json.loads(p.read_text())
        if s.get('state')=='awaiting_grade':yield d,s

def main():
    errors={}
    while True:
        for d,s in eligible():
            report=ROOT/'grades'/d.name/'result.json'
            if report.exists() or d.name in errors:continue
            try:
                target=ROOT/'incoming'/d.name;target.mkdir(exist_ok=False)
                assert sha(d/'final-source.tar.gz')==s['artifact']['sha256']
                shutil.copyfile(d/'final-source.tar.gz',target/'final-source.tar.gz');save(target/'summary.json',s)
                with (target/'grading.log').open('x') as out,(target/'grading-stderr.log').open('x') as err:
                    p=subprocess.run([sys.executable,'-B',str(ROOT/'grade_one.py'),'--job',d.name],
                                     stdin=subprocess.DEVNULL,stdout=out,stderr=err)
                r=json.loads(report.read_text())
                if p.returncode or r.get('grading_state')!='complete' or not r.get('grading_container_destroyed'):
                    raise RuntimeError('grading_or_cleanup_failed')
            except Exception as error:errors[d.name]=type(error).__name__;break
        hpath=ROOT/'health.json';h=json.loads(hpath.read_text()) if hpath.exists() else {}
        reports=[json.loads(p.read_text()) for p in (ROOT/'grades').glob('*/result.json')]
        n=sum(r.get('grading_state')=='complete' for r in reports)
        terminal=h.get('state') in ('generation_complete','needs_attention') and not h.get('active')
        remaining=[d.name for d,_ in eligible() if not (ROOT/'grades'/d.name/'result.json').exists()]
        save(ROOT/'grading-health.json',{'state':'needs_attention' if errors else
            'complete_for_available_artifacts' if terminal and not remaining else 'grading',
            'updated':time.time(),'scored':n,'errors':errors,'model_calls':0})
        if errors or terminal and not remaining:return
        time.sleep(3 if terminal else 15)

if __name__=='__main__':main()
