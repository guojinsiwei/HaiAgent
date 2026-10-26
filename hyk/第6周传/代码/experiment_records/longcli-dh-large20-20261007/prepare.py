"""Create an independent DH budget arm; never mutate historical runs."""
import hashlib
import json
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parent
OLD=ROOT.parent/'longcli-dh-raw-full20-20261004'
DSH=ROOT.parent/'longcli-dsh20-repair2-20261005'
REC=ROOT.parent/'longcli-retrac20-engineering-repair-20261006'

def main():
    for name in ('sources','compatibility'):
        shutil.copytree(OLD/name,ROOT/name,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    for name in ('common.py','environment.py','audit.py','net_transport.py','shared_wire.py','dh-source-manifest.json'):
        shutil.copyfile(OLD/name,ROOT/name)
    shutil.copyfile(OLD/'runner.py',ROOT/'historical_runner.py')
    for name in ('safe_process.py','grading_adapter.py','grade_one.py','grading_worker.py'):
        shutil.copyfile(REC/name,ROOT/name)
    # Mechanical capacity changes only. No prompt, schema or decision rule changes.
    p=ROOT/'shared_wire.py';s=p.read_text()
    s=s.replace("self.stats['api_requests']+=1", "if getattr(self,'budget',None) is not None:self.budget.claim()\n            self.stats['api_requests']+=1")
    s=s.replace('len(stripped)>64000','len(stripped)>524288');p.write_text(s)
    p=ROOT/'sources/bestfgs-project/src/bestfgs/lean_protocol.py'
    s=p.read_text();assert s.count('> 24000')==2
    p.write_text(s.replace('> 24000','> 524288'))
    p=ROOT/'grading_worker.py';p.write_text(p.read_text().replace("glob('retrac--*')","glob('dh--*')"))
    p=json.loads((DSH/'protocol.json').read_text())
    # Retain task/image/grader identities, remove stale small-budget inherited fields.
    protocol={k:p[k] for k in ('commit','tasks','model')}
    for row in protocol['tasks']:row['wall_seconds']=7200
    protocol.update(experiment=ROOT.name,methods=['dh'],total_trials=20,max_turns=800,max_tools=600,
        max_tokens=32768,context_tokens=1000000,context_headroom_tokens=65536,
        context_limit=(1000000-65536)*4,command_seconds=300,wall_seconds=7200,
        concurrency=4,cpu_per_task=2,memory_gib_per_task=8,pids_limit=256,
        temperature=0,thinking=False,actual_api_attempts_per_task=800,
        role_output_tokens={'action':32768,'monitor':32768,'advisor':32768},
        baseline='longcli-dh-raw-full20-20261004/recovery-counter-fix-v9',
        matched_dsh='longcli-dsh20-repair2-20261005',
        preserved={'route_search':False,'contrastive_predictions':False,'contrastive_mode':'orthogonal',
                   'memory':'DH original','context_compaction':'DH native excerpts, NOT DSH summarizer'},
        remaining_native_differences=['DH JSON actions versus DSH native tools',
          'DH stateless command shell versus DSH persistent sessions',
          'DH memory/monitor/advisor policies retained; DSH compaction/title policies not imported',
          'Task network none versus DSH internal network with API-only relay; provider client on host'],
        context_meter='DSH 0.2.0-rc.2 fixed density: UTF-16 chars/4 + message/block framing; heuristic, not exact tokenizer')
    (ROOT/'protocol.json').write_text(json.dumps(protocol,indent=2))
    old=json.loads((OLD/'dh-source-manifest.json').read_text())['hashes']
    changes={}
    for name,expected in old.items():
        file=ROOT/'sources/bestfgs-project/src/bestfgs'/name
        actual=hashlib.sha256(file.read_bytes()).hexdigest()
        if actual!=expected:changes[name]={'old':expected,'new':actual}
    assert set(changes)=={'lean_protocol.py'},changes
    (ROOT/'source-provenance.json').write_text(json.dumps({'base':str(OLD),'capacity_only_source_changes':changes,
        'detail':'Only argv/stdin maximum characters 24000 -> 524288; all other native source hashes identical.'},indent=2))

if __name__=='__main__':main()
