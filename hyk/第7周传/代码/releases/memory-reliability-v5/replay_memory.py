"""Replay two actual rejected v2 candidates; never replay commands or alter rewards."""
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'sources/bestfgs-project/src'))
from bestfgs.lean_memory import Memories

rows=json.loads((ROOT/'evidence/previous-rejected-candidates.json').read_text())
results=[]
for row in rows:
    evidence={e['id']:e for e in row['evidence']}
    store=Memories(reliable=True)
    # Historical file snapshots were not recorded in v2. Do not invent current versions.
    item,added=store.admit(row['candidate'],evidence,set(evidence),
                           lambda paths:{p:'unknown' for p in paths},current_scope=row['scope'])
    assert added and item['conclusion']==row['candidate']['conclusion']
    assert item['condition']==row['candidate']['condition']
    assert item['evidence_ids']==row['candidate']['evidence_ids']
    assert item['operation']=='' and item['repairs'][0]['field']=='operation'
    results.append(dict(trial=row['trial'],source=row['source'],source_sha256=row['sha256'],
        original_rejection=row['original_reason'],new_admission=True,repairs=item['repairs'],
        applicability=store.applicability(item,row['scope'],{p:'unknown' for p in item['targets']}),
        conclusion_and_evidence_preserved=True))
report=dict(candidates=len(results),admitted=len(results),model_calls=0,commands_executed=0,
            original_scores_unchanged=True,results=results)
(ROOT/'evidence/memory-replay.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps(report,ensure_ascii=False))
