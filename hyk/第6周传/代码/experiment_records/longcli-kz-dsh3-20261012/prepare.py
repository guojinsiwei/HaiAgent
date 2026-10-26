"""Freeze a NEW three-task migration regression; no credentials or paid calls."""
import json
from pathlib import Path
import shutil
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parent
DSH = Path('/var/tmp/lizh639-longcli-dsh20-20261005')
BASE = Path('/var/tmp/lizh639-longcli-dh-raw-full20-20261004')
TB = Path('/var/tmp/lizh639-tb4-taotoken-smoke-20261011')
TASKS = ['cs61_fa24_hog', 'cs61_fa24_cats', 'ap1400_2_hw35']

def main():
    assert not (ROOT/'protocol.json').exists(), 'Never overwrite a frozen campaign'
    for name in ('common.py', 'college_grader.py', 'input-manifest.json'):
        shutil.copy2(DSH/name, ROOT/name)
    (ROOT/'upstream').symlink_to(DSH/'upstream', target_is_directory=True)
    from common import sha, save
    protocol = json.loads((DSH/'protocol.json').read_text())
    rows = [next(r for r in protocol['tasks'] if r['task']==t) for t in TASKS]
    protocol.update(experiment=ROOT.name, methods=['kz'], tasks=rows,
        status='preparing', date='2026-10-12', historical_comparison='KZ original, no historical solver artifacts imported',
        comparison_limits=['TaoToken versus historical DeepSeek route; model revision not provably identical',
            'Native DSH execution/compaction versus historic KZ private harness',
            'Rollback frozen by user; historical KZ 1342 enabled it',
            'Native metadata tools count toward 600; historical shell counts differ',
            'Regression on three selected stable tasks, not unbiased benchmark ranking'],
        budget=dict(requests=800, tools=600, seconds=7200, context=1000000,
                    output=32768, headroom=65536, temperature=0, thinking=False,
                    cost_guard_cny=50, cost_guard_basis='historical 2/8 upper estimate, NOT TokenPlan invoice'),
        generation_resources=dict(concurrency_after_pilot=2,cpu_each=2,memory_gib_each=8,pids=256),
        compaction_temperature='native omitted; provider default',
        fresh_container_per_task=True, fresh_home_per_task=True, cross_task_memory=False,
        official_feedback_to_solver=False, no_automatic_retries=True,
        source_mode='current KZ 0.2.4 unmodified src; large-budget deployment overlay only')
    for row in rows:
        starter = BASE/('starter-'+row['task']+'.tar.gz')
        assert starter.is_file()
        row['starter_path']=str(starter)
        row['starter_sha256']=sha(starter)
        actual=subprocess.check_output(['docker','image','inspect',row['image'],'--format','{{.Id}}'],text=True).strip()
        assert actual==row['image_id']
    save(ROOT/'protocol.json',protocol)
    runtime=ROOT/'runtime'
    runtime.mkdir()
    shutil.copytree(TB/'build/node',runtime/'node')
    kz=runtime/'kz'; kz.mkdir()
    shutil.copytree(TB/'build/kz/node_modules',kz/'node_modules')
    with tarfile.open(ROOT/'candidate.tar.gz') as archive:
        archive.extractall(kz,filter='data')
    shutil.copy2(ROOT/'settings.mjs',kz/'settings.mjs')
    shutil.copy2(TB/'route-audit.mjs',kz/'route-audit.mjs')
    source=(kz/'config/kz.patch.yml').read_text()
    assert source.count('__KZ_PLUGIN_PATH__')==1
    (kz/'.runtime').mkdir()
    (kz/'.runtime/kz.patch.yml').write_text(source.replace('__KZ_PLUGIN_PATH__','/opt/kz/src/plugin.mjs'))
    route=(TB/'route2.patch.yml').read_text().replace('8192','32768').replace('128000','1000000')
    route=route.replace('tb4-smoke-settings','longcli-kz-large-settings').replace('/opt/kz/smoke-settings.mjs','/opt/kz/settings.mjs')
    (kz/'route.patch.yml').write_text(route)
    # Frozen inputs and full source, excluding native dependency tree which is copied once.
    files=[ROOT/n for n in ('protocol.json','common.py','college_grader.py','input-manifest.json','runner.py','container_run.py','offline.py','settings.mjs')]
    files += list((kz/'src').glob('*.mjs'))+list((kz/'config').glob('*.yml'))
    files += [kz/p for p in ('package-lock.json','package.json','.runtime/kz.patch.yml','route.patch.yml','route-audit.mjs','settings.mjs')]
    save(ROOT/'manifest.json',{'files':{str(p.relative_to(ROOT)):sha(p) for p in files},'paid_calls':0})
    (ROOT/'empty-tests').mkdir()
    print(json.dumps({'prepared':TASKS,'budget':protocol['budget']}))

if __name__=='__main__': main()
