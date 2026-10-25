"""Mechanical assembly of one sealed source shared by three incremental arms."""
from pathlib import Path
import hashlib
import json
import shutil

ROOT=Path(__file__).resolve().parent
WORKSPACE=ROOT.parents[1]
BASE=ROOT.parent/'longcli-dh-large20-20261007'
RELEASE=WORKSPACE/'releases/DH-routing-v1'

def main():
    for name in ('sources','tests'):
        if not (ROOT/name).exists():
            shutil.copytree(RELEASE/name,ROOT/name,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    if not (ROOT/'compatibility').exists():
        shutil.copytree(BASE/'compatibility',ROOT/'compatibility',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    for name in ('common.py','environment.py','docker_environment.py','audit.py','net_transport.py',
                 'shared_wire.py','safe_process.py','grading_adapter.py','grade_one.py','grade_accept.py',
                 'budget_adapter.py'):
        if not (ROOT/name).exists():shutil.copyfile(BASE/name,ROOT/name)
    p=json.loads((BASE/'protocol.json').read_text())
    names=['cs61_fa24_hog','cs61_fa24_scheme','cs61_fa24_ants','cmu15_445_p1',
           'ap1400_2_hw35','61810_fs','61810_pgtbl']
    by_task={r['task']:r for r in p['tasks']}
    p.update(experiment=ROOT.name,tasks=[by_task[n] for n in names],methods=['13','134','1342'],
             total_trials=21,concurrency=6,concurrency_per_arm=2,subgoals_enabled=True,
             source='DH-subgoal-v1 plus bounded error routes',
             arms={'13':{'local_correction':True,'reconnaissance':True,'critic':False,'backtracking':False},
                   '134':{'local_correction':True,'reconnaissance':True,'critic':True,'backtracking':False},
                   '1342':{'local_correction':True,'reconnaissance':True,'critic':True,'backtracking':True}},
             role_output_tokens={r:32768 for r in ('action','advisor','monitor','critic')},
             common={'subgoals':True,'memory':True,'orthogonal':True,'route_search':False,
                     'predictions':False,'cross_task_memory':False,'official_feedback_to_solver':False},
             limits={'critic_reviews':2,'checks_per_review':2,'local_corrections':3,'automatic_rollbacks':2},
             routing_trigger='evidence/format classified; unknown remains ordinary actor',
             task_selection='fixed before results: 3 Python, 2 C++, 2 OS; no cow/lock engineering incident',
             scoring='same frozen official LongCLIBench parser and separate fresh grading containers')
    (ROOT/'protocol.json').write_text(json.dumps(p,indent=2),encoding='utf-8')
    hashes={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest()
            for top in ('sources','compatibility') for f in (ROOT/top).rglob('*.py')}
    (ROOT/'source-provenance.json').write_text(json.dumps({'base':str(RELEASE),
        'shared_source_for_all_arms':True,'hashes':hashes},indent=2),encoding='utf-8')
    print(json.dumps({'assembled':True,'tasks':names,'trials':21}))

if __name__=='__main__':main()
