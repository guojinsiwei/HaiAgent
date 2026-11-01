"""Protect official scoring from cleanup faults; no scoring/parser changes."""
import json
import subprocess
import types
from common import ROOT,save
from safe_process import run_bounded


def cleanup_docker(*args,check=True,seconds=120):
    result=run_bounded(['docker',*map(str,args)],capture_output=True,text=True,
                       encoding='utf-8',errors='replace',timeout=seconds)
    if check and result.returncode:raise RuntimeError('Docker cleanup failed: '+result.stderr[-300:])
    return result


def install(grader):
    receipt={'model_calls':0,'errors':[],'owned':[],'official_grader_source_unchanged':True}
    owned=set()
    protocol=ROOT/'protocol.json'
    experiment=json.loads(protocol.read_text())['experiment'] if protocol.exists() else ROOT.name
    def docker(*args,check=True,seconds=120):
        if args[0]=='run':
            assert '--name' in args and '--label' in args
            assert 'experiment='+experiment in args,'Refuse foreign grader'
            owned.add(args[args.index('--name')+1])
            receipt['owned']=sorted(owned)
            save(ROOT/'grading-cleanup-health.json',receipt)
        try:
            result=run_bounded(['docker',*map(str,args)],capture_output=True,text=True,
                               encoding='utf-8',errors='replace',timeout=seconds)
        except subprocess.TimeoutExpired:
            if args[0]=='stop' and args[-1] in owned:
                receipt['errors'].append({'container':args[-1],'operation':'stop','error':'TimeoutExpired'})
                save(ROOT/'grading-cleanup-health.json',receipt)
                # The unchanged official grader can now SAVE the already computed
                # result in its finally block. Cleanup failure is reported separately.
                return subprocess.CompletedProcess(args,124,'','Owned grader stop timed out')
            raise
        if check and result.returncode:raise RuntimeError('Docker operation failed: '+result.stderr[-500:])
        return result
    grader.docker=docker
    grader.subprocess=types.SimpleNamespace(run=run_bounded,STDOUT=subprocess.STDOUT)
    return receipt
