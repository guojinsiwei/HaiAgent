"""Offline replay of actual routed outcomes up to first new activation only."""
import json,sys
from pathlib import Path
base=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(base/'projects/kz-native-orthogonal-trigger-20261017/native'))
from test_exploration_trigger import Runner
root=Path(__file__).parent
raw=json.loads((root/'raw.json').read_text(encoding='utf-8-sig'))
results=[]
for run in (r for r in raw['rows'] if r['arm']=='native-kz'):
    runner=Runner()
    for k,v in run['config'].items():setattr(runner.config,k,v)
    assessments={e['evidence_id']:e for e in run['events'] if e['event']=='execution_assessment'}
    exempt={e['evidence_id'] for e in run['events'] if e['event']=='error_route_execution_defect'}
    first=None
    for e in run['events']:
        if e['event']!='tool_call':continue
        runner.counts['tool_calls']+=1
        if e['evidence_id'] in exempt:continue
        r=e['result'];a=assessments[e['evidence_id']]
        row=dict(id=e['evidence_id'],return_code=r['return_code'],stdout=r['stdout'],stderr=r['stderr'],
          before=e['before'],after=e['after'],category=e['diagnostic_category'],timed_out=r['timed_out'],
          blocked=r['blocked'],capture_incomplete=r.get('output_truncated',False),
          terminal_projection_incomplete=False,dependency_after={})
        runner._contrastive_outcome(e['command'],row,a)
        if runner.contrastive_episode:
            first=dict(at=row['id'],line=e['line'],trigger=runner.events[-1]['trigger_evidence']);break
    results.append(dict(arm=run['arm'],task=run['task'],oldEpisodes=run['counts'].get('contrastive_episode_start',0),first=first))
(root/'replay-native.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps(results,ensure_ascii=False))
