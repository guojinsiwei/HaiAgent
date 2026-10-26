"""Keyless preparation only, in a fresh directory on the existing test server."""
import argparse,hashlib,json,shutil,subprocess,tarfile
from experiment import load,protocol_fields
from storage import atomic_json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--baseline-release',required=True,type=Path)
    args=parser.parse_args();BASE=args.baseline_release.resolve()
    if BASE==ROOT:raise RuntimeError('Baseline and candidate must differ')
    config=load(ROOT)
    assert not (ROOT/'runtime').exists(),'Refuse to overwrite prepared candidate'
    seal=json.loads((BASE/'ready.json').read_text())
    for name,h in seal['files'].items():assert sha(BASE/name)==h,name
    runtime=ROOT/'runtime';runtime.mkdir()
    with tarfile.open(BASE/'runtime-final.tar.gz') as archive:archive.extractall(runtime,filter='data')
    kz=runtime/'kz'
    with tarfile.open(ROOT/'source.tar.gz') as archive:archive.extractall(kz,filter='data')
    assert json.loads((kz/'package.json').read_text())['version']=='0.3.1'
    for name in ('container-run.mjs','deadline.mjs'):shutil.copy2(ROOT/name,kz/name)
    patch=kz/'.runtime/kz.patch.yml';text=patch.read_text()
    assert text.count('        budgetDisabled: true')==1
    if 'serverWallSeconds' not in text:
        text=text.replace('        budgetDisabled: true','        budgetDisabled: true\n        serverWallSeconds: 10800\n        artifactRoots: ["/results"]')
    else:
        assert 'serverWallSeconds: 10800' in text and 'artifactRoots: ["/results"]' in text
    patch.write_text(text)
    # Configuration, transport, compression and shared accounting stay frozen.
    common=['config/common.patch.yml','route.patch.yml','route-audit.mjs','shared-budget.mjs','boot-guard.mjs','.runtime/transport.patch.yml']
    tasks=json.loads((BASE/'tasks.json').read_text());tasks['tasks']=tasks['tasks'][:config['task_count']]
    tasks['selection']='First three of the frozen 30; no result-based reselection'
    (ROOT/'tasks.json').write_text(json.dumps(tasks,indent=2));(ROOT/'history.json').write_text('{}')
    dependencies=ROOT/'dependencies'
    dependencies.mkdir()
    shutil.copy2(BASE/'network_proxy.py',dependencies/'network_proxy.py')
    for task in tasks['tasks']:
        shutil.copytree(BASE/'official/tasks'/task['name'],dependencies/'official/tasks'/task['name'])
    files={str(p.relative_to(dependencies)):sha(p) for p in dependencies.rglob('*') if p.is_file()}
    atomic_json(dependencies/'ready.json',dict(files=files,source=str(BASE)))
    from build_runtime import build
    build()
    protocol=json.loads((BASE/'protocol.json').read_text())
    protocol.update(arms=['KZ-on-DSH 0.3.1 evidence-control-2'],parent_campaign=str(BASE),
        status='offline_acceptance_pending',total_trials=3,paired_tasks=None,max_trials_with_retry=6,results_reused=False,
        concurrency={'total':1,'per_arm':1},retry_policy='finish first pass; one final engineering-fault-only retry batch; no score-zero or valid wall-budget retries')
    protocol.update(protocol_fields(config))
    protocol['engineering_revision']='engineering-1'
    protocol['budget']['server_solver_seconds']=config['solver_seconds']
    protocol['common_hashes']={n:sha(kz/n) for n in common}
    with tarfile.open(BASE/'runtime-final.tar.gz') as archive:
        for name,digest in protocol['common_hashes'].items():
            if hashlib.sha256(archive.extractfile('kz/'+name).read()).hexdigest()!=digest:
                raise RuntimeError('Common runtime drift: '+name)
    protocol['source_sha256']=sha(ROOT/'source.tar.gz')
    protocol['tasks_sha256']=sha(ROOT/'tasks.json')
    (ROOT/'protocol.json').write_text(json.dumps(protocol,indent=2))
    (ROOT/'ready.json').write_text(json.dumps({'passed':False,'reason':'offline acceptance pending'}))
    print(json.dumps(dict(prepared=True,tasks=len(tasks['tasks']),paid_calls=0)))
if __name__=='__main__':main()
