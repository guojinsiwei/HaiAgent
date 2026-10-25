"""Keyless TB2 preparation using official sample names and full pinned tasks."""
import argparse,hashlib,json,shutil,subprocess,tarfile,tomllib
from pathlib import Path
from experiment import load,protocol_fields
from storage import atomic_json
ROOT=Path(__file__).resolve().parent
COMMIT='69671fbaac6d67a7ef0dfec016cc38a64ef7a77c'
NAMES=['build-cython-ext','chess-best-move','configure-git-webserver','fix-code-vulnerability','log-summary-date-ranges','polyglot-c-py','qemu-alpine-ssh','qemu-startup','regex-log','sqlite-with-gcov']
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--baseline-release',required=True,type=Path)
    base=parser.parse_args().baseline_release.resolve();config=load(ROOT)
    assert base!=ROOT and not (ROOT/'runtime').exists()
    seal=json.loads((base/'ready.json').read_text());assert seal['passed']
    for n,digest in seal['files'].items():assert sha(base/n)==digest,n
    source=ROOT/'official-source'
    assert subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()==COMMIT
    assert not subprocess.check_output(['git','-C',str(source),'status','--porcelain'],text=True).strip()
    runtime=ROOT/'runtime';runtime.mkdir()
    with tarfile.open(base/'runtime-final.tar.gz') as archive:archive.extractall(runtime,filter='data')
    kz=runtime/'kz'
    with tarfile.open(ROOT/'source.tar.gz') as archive:archive.extractall(kz,filter='data')
    assert json.loads((kz/'package.json').read_text())['version']=='0.3.2'
    for n in ('container-run.mjs','deadline.mjs'):shutil.copy2(ROOT/n,kz/n)
    tasks=[];dependencies=ROOT/'dependencies';dependencies.mkdir()
    shutil.copy2(base/'dependencies/network_proxy.py',dependencies/'network_proxy.py')
    for name in NAMES:
        task=tomllib.loads((source/name/'task.toml').read_text())
        tasks.append(dict(name=name,category=task.get('metadata',{}).get('category'),difficulty=task.get('metadata',{}).get('difficulty'),environment=task.get('environment',{}),agent=task.get('agent',{}),verifier=task.get('verifier',{})))
        shutil.copytree(source/name,dependencies/'official/tasks'/name)
    atomic_json(ROOT/'tasks.json',dict(benchmark='Terminal-Bench 2.0',commit=COMMIT,selection='Official terminal-bench-sample@2.0 names; pinned full terminal-bench@2.0 task contents; selected before outcomes',population=89,tasks=tasks))
    atomic_json(ROOT/'history.json',{})
    atomic_json(dependencies/'ready.json',dict(files={p.relative_to(dependencies).as_posix():sha(p) for p in dependencies.rglob('*') if p.is_file()},source_commit=COMMIT))
    from bounded_runtime import configure
    configure(runtime)
    from build_runtime import build
    build()
    common=['config/common.patch.yml','route.patch.yml','route-audit.mjs','shared-budget.mjs','boot-guard.mjs','.runtime/transport.patch.yml']
    protocol=dict(benchmark='Terminal-Bench 2.0',commit=COMMIT,arms=['Pure DSH','KZ-on-DSH 0.3.2 evidence-control-3'],paired_tasks=10,
        endpoint='https://api.taotoken.net/token/v1/messages',model='deepseek-flash',thinking=False,temperature=0,
        budget=dict(server_solver_seconds=2700,requests_per_trial=120,tools_per_trial=180,estimate_peak_cny_per_trial=4,estimate_peak_cny_campaign=80,context_tokens=128000,output_tokens=16384),
        fresh_container=True,fresh_home=True,cross_task_memory=False,original_task_resources=True,original_official_verifier=True,
        arm_order='Task1 DSH then KZ; task2 KZ then DSH; alternate thereafter; global concurrency1',
        scope='Official ten-name sample, not a full89 score; one trial per arm/task; common45minute cap is a custom bounded setting',
        role_accounting='KZ roles and compaction charged to KZ; identical provider accounting and tool limits for pure DSH',
        parent_runtime=str(base),status='offline_acceptance_pending',engineering_revision='task-fault-isolation-1',
        common_hashes={n:sha(kz/n) for n in common},bounded_design=json.loads((ROOT/'budget-profile.json').read_text()),
        source_sha256=sha(ROOT/'source.tar.gz'),tasks_sha256=sha(ROOT/'tasks.json'))
    protocol.update(protocol_fields(config));atomic_json(ROOT/'protocol.json',protocol)
    atomic_json(ROOT/'ready.json',dict(passed=False,reason='offline acceptance pending'))
    print(json.dumps(dict(prepared=True,paired_tasks=10,trials=20,paid_calls=0)))
if __name__=='__main__':main()
