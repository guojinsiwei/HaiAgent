from pathlib import Path
import json,shutil,tarfile
OLD=Path(__file__).resolve().parent
ROOT=OLD.parent/'suz-osworld30-fresh-20261025'
ROOT.mkdir(exist_ok=False)
SOURCE=OLD/'repair3'
for name in ['common.py','environment.py','worker.py','launch.py','model-config.json','experiment.json',
    'task-manifest.json','assets-preflight.json','cache_assets.py','grading_cache.py','desktop_ready.py',
    'test_grading_cache.py','test_desktop_ready.py','preflight-environment.py']:
    shutil.copy2(SOURCE/name,ROOT/name)
old_remote='/data/share/lizh639/suz-osworld30-20261024'
p=ROOT/'common.py';s=p.read_text().replace("ROOT.parent/'budget.sqlite'","ROOT/'budget.sqlite'").replace("'repair-jobs.json'","'jobs.json'")
p.write_text(s)
p=ROOT/'environment.py';s=p.read_text().replace("ROOT.parent/'cpu-vm-start.lock'",f"Path('{old_remote}/cpu-vm-start.lock')")
s=s.replace("'experiment':'suz-osworld30-20261024'","'experiment':'suz-osworld30-fresh-20261025'");p.write_text(s)
p=ROOT/'launch.py';s=p.read_text().replace("'repair-jobs.json'","'jobs.json'");p.write_text(s)
p=ROOT/'worker.py';s=p.read_text().replace('except Exception as exc:',"except KeyboardInterrupt:\n    status.update(stage='cancelled_by_user',cancelled_at=time.time())\nexcept Exception as exc:")
p.write_text(s)
p=ROOT/'preflight-environment.py';s=p.read_text().replace("ROOT.parent/'repair3-final.tar.gz'",f"Path('{old_remote}/repair3-final.tar.gz')")
p.write_text(s)
p=ROOT/'experiment.json';cfg=json.loads(p.read_text());cfg.update(name=ROOT.name,fresh_comparison=True,
    prior_results_reused=False,independent_budget=True,reference_experiment='suz-osworld30-20261024',
    cohort='same 30 task ids and checksums, fresh VM and agent for every arm/task')
p.write_text(json.dumps(cfg,indent=2))
rows=json.loads((ROOT/'task-manifest.json').read_text())['tasks']
jobs=[{'index':i,'id':row['id'],'mode':mode} for i,row in enumerate(rows)
    for mode in (['opencua_baseline','suz'] if i%2==0 else ['suz','opencua_baseline'])]
(ROOT/'jobs.json').write_text(json.dumps(jobs,indent=2))
(ROOT/'AGENTS.md').write_text('''# Fresh OSWorld comparison
- User authorized a new independent CNY 480 total, CNY 8 per arm/task, including all auxiliary calls.
- Same 30 tasks per arm; exactly 60 fresh runs. No historical scores substituted or merged.
- Freeze repaired SUZ source and GLM-5.3-Flash configuration for both arms.
- CPU desktops only. No GPUs or GPT automations. Never print credentials.
- Keep old experiments, cancelled repairs, scores, artifacts and ledgers intact.
- Validate startup and grading before inference; preserve paid work on grading failure.
''')
with tarfile.open(ROOT/'deployment.tar.gz','w:gz') as out:
    for p in sorted(ROOT.iterdir()):
        if p.is_file() and p.name!='deployment.tar.gz':out.add(p,arcname=p.name)
    source=OLD.parent/'SUZ-repair3'
    for p in sorted(source.rglob('*')):
        if p.is_file() and '__pycache__' not in p.parts:out.add(p,arcname=str(Path('SUZ')/p.relative_to(source)))
print(json.dumps({'project':str(ROOT),'jobs':len(jobs),'total_cny':480,'per_run_cny':8}))
