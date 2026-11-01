"""Fresh official Docker grading, once per immutable source artifact."""
import argparse
import ast
import json
import logging
import math
from pathlib import Path
import re
import shutil
import subprocess
import uuid
from common import ROOT,sha,save,import_tree

def docker(*args,check=True,seconds=120):
    result=subprocess.run(['docker',*map(str,args)],capture_output=True,text=True,
        encoding='utf-8',errors='replace',timeout=seconds)
    if check and result.returncode: raise RuntimeError('Docker operation failed: '+result.stderr[-500:])
    return result

def official_parser():
    harness=ROOT/'upstream/terminal_bench/harness/harness.py'
    tree=ast.parse(harness.read_text())
    namespace={'logger':logging.getLogger('paired10')}
    for filename in ('base_parser.py','pytest_parser.py'):
        path=ROOT/'upstream/terminal_bench/parsers'/filename
        parsed=ast.parse(path.read_text())
        parsed.body=[n for n in parsed.body if not (isinstance(n,ast.ImportFrom)
                    and (n.module or '').startswith('terminal_bench'))]
        exec(compile(parsed,str(path),'exec'),namespace)
    functions=[next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name==name)
               for name in ('_round_sig','_compute_pytest_metrics_from_content')]
    exec(compile(ast.Module(body=functions,type_ignores=[]),str(harness),'exec'),namespace)
    parser=namespace['_compute_pytest_metrics_from_content']
    assert parser('=== short test summary info ===\nPASSED t.py::a\nFAILED t.py::b')[0:2]==(0,0.5)
    return parser

def grade(job,archive,expected,fixture=False):
    protocol=json.loads((ROOT/'protocol.json').read_text())
    selected=[r for r in protocol['tasks'] if job.endswith('--'+r['task'])]
    assert len(selected)==1 and job.split('--')[0] in ('raw','bestfgs-v6.1','orthogonal-v8','fixture','fixture8','fixture-preserved','roundtrip'), 'Unknown job'
    row=selected[0]
    assert sha(archive)==expected,'Artifact integrity mismatch'
    manifest=json.loads((ROOT/'input-manifest.json').read_text())
    for name,hash_value in manifest['files'].items():
        if '/tests/' in name or name.endswith('run-tests.sh') or '/parsers/' in name or name.endswith('harness.py'):
            assert sha(ROOT/name)==hash_value,'Official grader source changed'
    assert docker('image','inspect',row['image'],'--format','{{.Id}}').stdout.strip()==row['image_id']
    # College storage admission floor disabled by the user's existing policy.
    # Actual ENOSPC still fails explicitly; no unrelated data is ever deleted.
    output=ROOT/('fixture-grades' if fixture else 'grades')/job
    output.mkdir(parents=True,exist_ok=False)
    imported=output/'source'; import_tree(archive,imported)
    assert (imported/row['project']).is_dir(),'Project missing from frozen artifact'
    name='longcli-paired10-'+uuid.uuid4().hex[:12]
    cpuset='0-7' if row['index']%2==0 else '8-15'
    docker('run','-d','--name',name,'--label','experiment='+protocol['experiment'],
        '--cpuset-cpus',cpuset,'--cpus','8','--memory','8g','--pids-limit','256','-e','TEST_DIR=/tests',
        '-w','/app',row['image_id'],'sleep','infinity')
    result=dict(job=job,task=row['task'],artifact_sha256=expected,image_id=row['image_id'],container=name,
                grading_cpu=8,grading_memory_gib=8,grading_cpuset=cpuset,
                official_success=None,grading_state='failed',fixture=fixture)
    try:
        # Remove ONLY the app directory inside this newly created owned container.
        docker('exec',name,'python3','-c',
            'from pathlib import Path; import shutil; p=Path("/app"); '
            'assert p.is_dir() and not p.is_symlink(); '
            '[shutil.rmtree(q) if q.is_dir() and not q.is_symlink() else q.unlink() for q in p.iterdir()]')
        docker('cp',str(imported)+'/.',name+':/app/')
        task=ROOT/'upstream/tasks_long_cli'/row['task']
        docker('cp',task/'tests',name+':/tests')
        docker('cp',task/'run-tests.sh',name+':/tests/run-tests.sh')
        with (output/'console.log').open('x') as log:
            p=subprocess.run(['docker','exec',name,'timeout',str(int(row['test_seconds'])),
                'bash','/tests/run-tests.sh'],stdout=log,stderr=subprocess.STDOUT,
                timeout=row['test_seconds']+60)
        result['script_exit']=p.returncode
        docker('cp',name+':/app/test_output',output)
        score=json.loads((output/'test_output/f2p_score.json').read_text())
        assert score['is_pass'] in (0,1) and math.isfinite(float(score['step_score']))
        content=(output/'test_output/p2p_output.txt').read_text(errors='replace')
        p2p=official_parser()(content)
        assert p2p[2],'No P2P checks parsed: grader failure, not a zero score'
        f2p_text=(output/'test_output/f2p_output.txt').read_text(errors='replace')
        result.update(grading_state='complete',f2p=score,p2p_is_pass=p2p[0],p2p_step_score=p2p[1],
            p2p_count=len(p2p[2]),p2p_cases=p2p[2],f2p_output_nonempty=bool(f2p_text.strip()),
            official_success=bool(score['is_pass'] and p2p[0]))
        assert p.returncode!=124,'Official grader timeout'
    except Exception as error:
        result.update(grading_state='failed',official_success=None,error_type=type(error).__name__,error=str(error)[:500])
    finally:
        docker('stop','-t','3',name,check=False)
        save(output/'result.json',result)
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--job',required=True); p.add_argument('--archive',type=Path,required=True)
    p.add_argument('--sha256',required=True); p.add_argument('--fixture',action='store_true'); a=p.parse_args()
    result=grade(a.job,a.archive,a.sha256,a.fixture); print(json.dumps(result),flush=True)
    raise SystemExit(0 if result['grading_state']=='complete' else 1)
