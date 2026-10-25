"""New frozen repair5 campaign, only public scripts/source/inputs; zero model calls."""
import json
from pathlib import Path
import shutil
import subprocess
import tarfile

ROOT=Path(__file__).resolve().parent
PREVIOUS=Path('/var/tmp/lizh639-longcli-kz-dsh3-20261012')

def main():
    assert not (ROOT/'protocol.json').exists(), 'Never overwrite a prepared experiment'
    for name in ('common.py','college_grader.py','input-manifest.json'):
        shutil.copy2(PREVIOUS/name,ROOT/name)
    (ROOT/'upstream').symlink_to((PREVIOUS/'upstream').resolve(),target_is_directory=True)
    from common import save,sha
    previous=json.loads((PREVIOUS/'protocol.json').read_text())
    rows=previous['tasks']
    assert [r['task'] for r in rows]==['cs61_fa24_hog','cs61_fa24_cats','ap1400_2_hw35']
    for row in rows:
        assert sha(row['starter_path'])==row['starter_sha256']
        assert subprocess.check_output(['docker','image','inspect',row['image'],'--format','{{.Id}}'],text=True).strip()==row['image_id']
    protocol=dict(experiment=ROOT.name,date='2026-10-13',commit=previous['commit'],tasks=rows,methods=['kz'],total_trials=3,
        model='deepseek-flash',provider_route='https://api.taotoken.net/token',thinking='disabled',temperature=0,
        source_version='KZ-DSH-0.2.6',budget=previous['budget'],generation_resources=previous['generation_resources'],
        grading_resources=previous['grading_resources'],compaction_temperature=previous['compaction_temperature'],
        fresh_container_per_task=True,fresh_home_per_task=True,cross_task_memory=False,official_feedback_to_solver=False,
        no_automatic_retries=True,status='preparing',known_upstream_defects=previous['known_upstream_defects'],
        comparison_limits=previous['comparison_limits'],previous_campaign=PREVIOUS.name,
        previous_protocol_sha256=sha(PREVIOUS/'protocol.json'),backtracking=False,
        changes=['KZ 0.2.6 recovery clock/episode lifecycle','top-level Bash pipeline receipt telemetry',
                 'subgoal lifecycle/explicit silent test checks','repair4 memory/evidence fixes and atomic native execution',
                 'explicit INSTRUCTION.md shared by all roles'],
        budget_definition='800 all-role provider streams/attempts incl compaction; 600 native+KZ metadata tools; 7200s; unchanged from prior three-task run',
        pilot_policy='hog first, then cats/ap35 up to two concurrent; engineering failure stops new admissions; preserve results; no paid retry',
        independence='Detached server supervisor holds key in memory; local computer may disconnect or power off; no GPT automations or email')
    assert protocol['budget']==dict(requests=800,tools=600,seconds=7200,context=1000000,output=32768,headroom=65536,temperature=0,thinking=False,cost_guard_cny=50,cost_guard_basis='historical 2/8 upper estimate, NOT TokenPlan invoice')
    save(ROOT/'protocol.json',protocol)
    runtime=ROOT/'runtime';runtime.mkdir()
    shutil.copytree(PREVIOUS/'runtime/node',runtime/'node',symlinks=True)
    kz=runtime/'kz';kz.mkdir()
    shutil.copytree(PREVIOUS/'runtime/kz/node_modules',kz/'node_modules',symlinks=True)
    with tarfile.open(ROOT/'candidate.tar.gz') as archive:archive.extractall(kz,filter='data')
    assert json.loads((kz/'package.json').read_text())['version']=='0.2.6'
    source_manifest=json.loads((ROOT/'source-manifest.json').read_text())
    for name,expected in source_manifest['files'].items():assert sha(kz/name)==expected,name
    shutil.copy2(ROOT/'settings.mjs',kz/'settings.mjs')
    shutil.copy2(ROOT/'kz-boot-guard.mjs',kz/'kz-boot-guard.mjs')
    shutil.copy2(PREVIOUS/'runtime/kz/route-audit.mjs',kz/'route-audit.mjs')
    shutil.copy2(PREVIOUS/'runtime/kz/route.patch.yml',kz/'route.patch.yml')
    subprocess.run([str(runtime/'node/bin/node'),str(kz/'scripts/prepare-config.mjs'),'--longcli','--plugin-path','/opt/kz/src/plugin.mjs'],check=True)
    (ROOT/'empty-tests').mkdir()
    files=[p for p in ROOT.iterdir() if p.is_file() and p.suffix in ('.py','.mjs','.json')]
    files += [kz/name for name in source_manifest['files']]
    files += [kz/name for name in ('settings.mjs','kz-boot-guard.mjs','route-audit.mjs','route.patch.yml','.runtime/kz.patch.yml')]
    save(ROOT/'manifest.json',dict(files={str(p.relative_to(ROOT)):sha(p) for p in files},paid_calls=0))
    print(json.dumps(dict(prepared=[r['task'] for r in rows],version='0.2.6',budget_unchanged=True)))

if __name__=='__main__':main()
