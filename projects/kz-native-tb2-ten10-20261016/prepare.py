import hashlib,json,shutil,tarfile
from pathlib import Path
from storage import atomic_json
from experiment import load,protocol_fields
ROOT=Path(__file__).resolve().parent
BASE=Path('/mnt/sdb/home/lizh639/tb2-kz-dsh-paired10-20261016')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    assert not (ROOT/'dependencies').exists()
    for n in ('tasks.json','dependencies/ready.json'):
        assert (BASE/n).is_file()
    shutil.copytree(BASE/'dependencies',ROOT/'dependencies')
    shutil.copy2(BASE/'tasks.json',ROOT/'tasks.json')
    shutil.copy2(BASE/'runtime-final.tar.gz',ROOT/'runtime-final.tar.gz')
    shutil.copytree(BASE/'environment-locks',ROOT/'environment-locks')
    for n,d in json.loads((ROOT/'dependencies/ready.json').read_text())['files'].items():assert sha(ROOT/'dependencies'/n)==d
    atomic_json(ROOT/'history.json',{})
    with tarfile.open(ROOT/'native-runtime.tar.gz','w:gz') as a:
        for p in sorted((ROOT/'native').rglob('*')):
            if p.is_file() and '__pycache__' not in p.parts:a.add(p,arcname='kz-standalone/'+p.relative_to(ROOT/'native').as_posix())
    tasks=json.loads((ROOT/'tasks.json').read_text())['tasks']
    profile=json.loads((BASE/'budget-profile.json').read_text());profile.update(campaign_limit_microcny=40000000,jobs=[f'first-{i+1:02d}-native-kz-{t["name"]}' for i,t in enumerate(tasks)])
    atomic_json(ROOT/'budget-profile.json',profile)
    protocol=json.loads((BASE/'protocol.json').read_text())
    for k in ('common_hashes','source_sha256','bounded_design'):protocol.pop(k,None)
    protocol.update(arms=['Native KZ2.0 repair1'],arm_order='Frozen ten tasks; sequential one native trial per task',parent_runtime=str(BASE),native_source='experiment_records/tb4-runtime-repair-20261015/native',
        status='offline_acceptance_pending',engineering_revision='native-tb2-timeout-handoff-1',role_accounting='All four native roles, retries and corrections charged to native KZ',
        comparison_limit='Standalone executor differs from DSH; older paired KZ task1 hit unintended 900s timeout and has no valid score; never compare missing score as zero.')
    protocol['budget']['estimate_peak_cny_campaign']=40
    protocol.update(protocol_fields(load(ROOT)));atomic_json(ROOT/'protocol.json',protocol)
    atomic_json(ROOT/'ready.json',dict(passed=False))
    print(json.dumps(dict(prepared=True,trials=10,budget=40,paid_calls=0)))
if __name__=='__main__':main()
