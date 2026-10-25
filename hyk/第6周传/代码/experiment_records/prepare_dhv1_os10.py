"""Create a fresh DHv1-only campaign from audited harness and pinned inputs."""
import json
from pathlib import Path
import shutil
import tarfile
import hashlib

WORKSPACE = Path(__file__).resolve().parents[1]
OLD = WORKSPACE/'experiment_records/longcli-dh-raw-full20-20261004'
RELEASE = WORKSPACE/'releases/DHv1'
NAME = 'longcli-dhv1-os10-20261004'
ROOT = WORKSPACE/'experiment_records'/NAME

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    ROOT.mkdir(exist_ok=False)
    names = ('common.py','runner.py','parallel_worker.py','cube_prepare.py','fixture_runner.py',
             'audit.py','shared_wire.py','net_transport.py','admission.py','launch.py',
             'college_grader.py','validate_college.py','relay.py')
    for name in names:
        shutil.copy2(OLD/name, ROOT/name)
    for source in (RELEASE/'harness').glob('*.py'):
        if source.name != 'common.py': shutil.copy2(source,ROOT/source.name)
    for name in ('sources','compatibility'):
        shutil.copytree(RELEASE/name,ROOT/name,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    p=json.loads((OLD/'protocol.json').read_text())
    previous=json.loads((WORKSPACE/'experiment_records/longcli-threeway-engineering-20261003/protocol.json').read_text())
    old_ids={r['task'] for r in previous['tasks']}
    rows=[r for r in p['tasks'] if r['task'] not in old_ids]
    assert len(old_ids)==10 and len(rows)==10 and all(r['task'].startswith('61810_') for r in rows)
    rows=[dict(r,index=i) for i,r in enumerate(rows)]
    p.update(experiment=NAME,tasks=rows,methods=['dh'],total_trials=10,expectation_enabled=True,
             source_releases={'dh':'DHv1 + verified engineering boundary fixes'},
             context_windows={'dh':'48000 characters, native memory protection'},
             assignment='One DH arm, alternating task index across two workers, two slots each',
             pilot_policy='Zero-API fixture preflight on all 10 tasks before paid launch',
             status='preparing_not_started',excluded_common10=sorted(old_ids))
    (ROOT/'protocol.json').write_text(json.dumps(p,indent=2,ensure_ascii=False),encoding='utf-8')
    for worker in (0,1): shutil.copy2(OLD/f'resources-{worker}.json',ROOT/f'resources-{worker}.json')
    source_hashes={f.relative_to(ROOT).as_posix():digest(f) for folder in ('sources','compatibility')
                   for f in (ROOT/folder).rglob('*') if f.is_file()}
    (ROOT/'dh-source-manifest.json').write_text(json.dumps(dict(name='DHv1',hashes=source_hashes,
        expectation_enabled=True,contrastive_predictions=False,route_search=False),indent=2),encoding='utf-8')
    # Adapt only deployment plumbing, not the algorithm or thresholds.
    runner=(ROOT/'runner.py').read_text()
    runner=runner.replace("contrastive_predictions=False,context_chars=protocol['context_limit']",
                          "contrastive_predictions=False,expectation_enabled=True,context_chars=protocol['context_limit']")
    (ROOT/'runner.py').write_text(runner,encoding='utf-8')
    wire=(ROOT/'shared_wire.py').read_text()
    wire=wire.replace('self.config, self.audit, self.role = config, audit, role',
                      'self.config, self.audit, self.role = config, audit, role\n        self.request_deadline = None')
    wire=wire.replace('until=time.monotonic()+self.config.max_wall_time_seconds',
                      'until=time.monotonic()+self.config.max_wall_time_seconds\n        if self.request_deadline is not None:\n            until=min(until,self.request_deadline)')
    (ROOT/'shared_wire.py').write_text(wire,encoding='utf-8')
    relay=(ROOT/'relay.py').read_text().replace('longcli-dh-raw-full20-20261004',NAME)
    (ROOT/'relay.py').write_text(relay,encoding='utf-8')
    launcher=(OLD/'Start-DH-RAW-Full20.ps1').read_text()
    launcher=launcher.replace('longcli-dh-raw-full20-20261004',NAME)
    launcher=launcher.replace('DH / RAW - Full LongCLI (40 trials)','DHv1 - LongCLI OS10')
    launcher=launcher.replace('DH versus RAW: 20 LongCLI tasks per arm, 40 fresh trials.','DHv1 only: 10 MIT 6.1810 tasks, 10 fresh trials; no RAW or common10.')
    launcher=launcher.replace('DH=v9+recovery counter repair; predictions disabled.','DHv1=expected observation enabled + repaired engineering; graph search and two-candidate predictions disabled.')
    launcher=launcher.replace('tasks_per_arm=20;trials=40','tasks_per_arm=10;trials=10')
    (ROOT/'Start-DHv1-OS10.ps1').write_text(launcher,encoding='utf-8')
    # Bundles contain source/config only, not historical logs or credentials.
    for kind in ('solver','college'):
        with tarfile.open(ROOT/(kind+'-deployment.tgz'),'x:gz') as archive:
            files=[f for f in ROOT.glob('*') if f.suffix in ('.py','.json')]
            if kind=='solver':
                files += [f for folder in ('sources','compatibility') for f in (ROOT/folder).rglob('*') if f.is_file()]
            for f in files: archive.add(f,arcname=f.relative_to(ROOT).as_posix(),recursive=False)
    print(json.dumps(dict(campaign=NAME,tasks=[r['task'] for r in rows],trials=10,model=p['model'],concurrency=4)))

if __name__=='__main__':main()
