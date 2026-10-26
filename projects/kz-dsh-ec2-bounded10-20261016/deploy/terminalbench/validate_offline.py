"""Offline suites only: never imports or invokes a campaign entry point."""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from storage import atomic_json

ROOT=Path(__file__).resolve().parent


def source_hashes(project, deployment=ROOT):
    files={}
    for folder in ('src','scripts','tests','config'):
        for path in (project/folder).rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts:
                files['project/'+path.relative_to(project).as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
    for name in ('package.json','package-lock.json'):
        files['project/'+name]=hashlib.sha256((project/name).read_bytes()).hexdigest()
    for path in deployment.iterdir():
        if path.suffix in ('.py','.mjs') or path.name=='experiment.json':
            files['deployment/'+path.name]=hashlib.sha256(path.read_bytes()).hexdigest()
    return files


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--project',required=True,type=Path)
    parser.add_argument('--node',default=shutil.which('node'))
    args=parser.parse_args();project=args.project.resolve()
    if not args.node:raise RuntimeError('Explicit Linux Node >=24 runtime required')
    before=source_hashes(project)
    suites=[('node',[args.node,'--test','--test-reporter=tap',*[str(p) for p in sorted((project/'tests').glob('*.test.mjs'))]],project),
            ('python',[sys.executable,'-m','unittest','discover','-s',str(ROOT),'-p','test_*.py','-v'],ROOT)]
    if sys.platform=='linux':
        suites.append(('deadline',[args.node,'--test','--test-reporter=tap',str(ROOT/'test_deadline.mjs'),str(ROOT/'test-provider-guard.mjs'),str(ROOT/'test_bounded_transport.mjs')],ROOT))
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PATH=str(Path(args.node).resolve().parent)+os.pathsep+os.environ.get('PATH',''))
    for key in list(env):
        if key.endswith(('API_KEY','AUTH_TOKEN')):env.pop(key,None)
    results=[]
    for name,command,cwd in suites:
        log=ROOT/(name+'-engineering.log')
        with log.open('w') as output:
            try:code=subprocess.run(command,cwd=cwd,env=env,stdout=output,stderr=subprocess.STDOUT,timeout=900).returncode
            except subprocess.TimeoutExpired:code=124
        text=log.read_text(errors='replace')
        counts={k:int(v) for k,v in re.findall(r'^# (tests|pass|fail|skipped|cancelled) (\d+)$',text,re.M)}
        if name=='python':
            match=re.search(r'Ran (\d+) tests?',text)
            counts={'tests':int(match.group(1)) if match else 0}
        results.append(dict(suite=name,exit_code=code,counts=counts,log=log.name,
                            log_sha256=hashlib.sha256(log.read_bytes()).hexdigest()))
    report=dict(schema_version=1,platform=sys.platform,source_hashes=before,suites=results,
                passed=all(r['exit_code']==0 and r['counts'].get('tests',0)>0 for r in results)
                       and before==source_hashes(project),model_acceptance=False)
    atomic_json(ROOT/'validation.json',report)
    print(json.dumps(report,indent=2));return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
