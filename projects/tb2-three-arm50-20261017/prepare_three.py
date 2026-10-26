import hashlib,json,random,shutil,subprocess,tarfile,tomllib
from pathlib import Path
ROOT=Path(__file__).resolve().parent
BASE=ROOT.parent/'tb2-kz-dsh-transport1-20261017'
NATIVE=ROOT.parent/'tb2-native-kz-tls3-20261017'
COMMIT='69671fbaac6d67a7ef0dfec016cc38a64ef7a77c'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(name,value):(ROOT/name).write_text(json.dumps(value,indent=2))
def main():
    assert not (ROOT/'launch-once.marker').exists()
    source=ROOT/'official-source'
    assert subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()==COMMIT
    assert not subprocess.check_output(['git','-C',str(source),'status','--porcelain'],text=True).strip()
    population=sorted(p.parent.name for p in source.glob('*/task.toml'));assert len(population)==89
    names=random.Random(20261017).sample(population,50)
    deps=ROOT/'dependencies';deps.mkdir(exist_ok=True)
    shutil.copy2(BASE/'dependencies/network_proxy.py',deps/'network_proxy.py')
    tasks=[]
    for n in names:
        data=tomllib.loads((source/n/'task.toml').read_text())
        tasks.append(dict(name=n,category=data.get('metadata',{}).get('category'),difficulty=data.get('metadata',{}).get('difficulty'),environment=data.get('environment',{}),agent=data.get('agent',{}),verifier=data.get('verifier',{})))
        shutil.copytree(source/n,deps/'official/tasks'/n,dirs_exist_ok=True)
    save('tasks.json',dict(benchmark='Terminal-Bench 2.0',commit=COMMIT,population=89,seed=20261017,selection='Uniform random sample without replacement from sorted official task names, frozen before results',tasks=tasks))
    save('history.json',{})
    save('dependencies/ready.json',dict(files={p.relative_to(deps).as_posix():sha(p) for p in deps.rglob('*') if p.is_file() and p.name!='ready.json'},source_commit=COMMIT))
    if not (ROOT/'venv').exists():(ROOT/'venv').symlink_to(BASE/'venv',target_is_directory=True)
    (ROOT/'environment-locks').mkdir(exist_ok=True)
    for n in ('python-runtime.tar.gz',):shutil.copy2(NATIVE/n,ROOT/n)
    for n in ('verifier-deps.tar.gz','verifier-deps-provenance.json'):shutil.copy2(BASE/n,ROOT/n)
    runtime=ROOT/'runtime';runtime.mkdir(exist_ok=True)
    with tarfile.open(BASE/'runtime-final.tar.gz') as tar:tar.extractall(runtime,filter='data')
    for d in ('src','tests'):shutil.copytree(ROOT/'latest-dsh'/d,runtime/'kz'/d,dirs_exist_ok=True)
    with tarfile.open(ROOT/'native-runtime.tar.gz','w:gz') as tar:tar.add(ROOT/'native',arcname='kz-standalone',filter=lambda i:None if '__pycache__' in i.name else i)
    from build_runtime import build
    build()
    from queue_policy import initial_rows
    rows=initial_rows(names,{})
    profile=json.loads((BASE/'budget-profile.json').read_text());profile.update(campaign_limit_microcny=600000000,task_limit_microcny=4000000,jobs=[r['job'] for r in rows])
    save('budget-profile.json',profile)
    from experiment import load,protocol_fields
    config=load(ROOT)
    protocol=dict(benchmark='Terminal-Bench 2.0',commit=COMMIT,arms=['native-kz','kz-dsh','dsh'],paired_tasks=50,endpoint=profile['endpoint'],model=profile['model'],thinking=False,temperature=0,budget=dict(server_solver_seconds=2700,requests_per_trial=120,tools_per_trial=180,estimate_peak_cny_per_trial=4,estimate_peak_cny_campaign=600),algorithm='orthogonal-learning-20261017',selection=names,seed=20261017,fresh_container=True,cross_task_memory=False,original_official_verifier=True,arm_order='Rotate starting arm every task',disk_policy='6 slots / 2 per arm; dynamic admission reserves 12 GiB headroom plus max(12 GiB, twice requested task storage) per active trial; quarantine reserves 30 GiB')
    protocol.update(protocol_fields(config));save('protocol.json',protocol)
    save('ready.json',dict(passed=False,reason='Linux offline acceptance pending'))
    save('source-lock.json',dict(files={p.relative_to(ROOT).as_posix():sha(p) for base in [ROOT/'native',ROOT/'runtime/kz/src'] for p in base.rglob('*') if p.is_file() and '__pycache__' not in p.parts}))
    print(json.dumps(dict(tasks=50,trials=150,first_tasks=names[:5],paid_calls=0)))
if __name__=='__main__':main()
