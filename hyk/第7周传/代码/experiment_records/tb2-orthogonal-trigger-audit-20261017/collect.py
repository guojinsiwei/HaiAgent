"""Read-only trace/source collection. No model calls, no remote changes."""
import collections,hashlib,json
from pathlib import Path
base=Path('/mnt/sdb/home/lizh639')
cohorts=['tb2-kz-dsh-paired10-20261016','tb2-kz-dsh-repair7-20261017','tb2-native-kz-ten10-20261016','tb2-native-kz-repair3-20261016','tb2-native-kz-tls3-20261017']
selected={}
for name in cohorts:
 root=base/name
 for row in json.loads((root/'admissions.json').read_text())['rows']:
  if row['arm'] not in ['kz-dsh','native-kz'] or not row.get('result',{}).get('engineering_clean'):continue
  selected[(row['arm'],row['task'])]=(root,row)
out={'rows':[],'sources':{}}
for (arm,task),(root,row) in sorted(selected.items()):
 trial=Path(row['result']['trial']);live=trial/'agent/live'
 item={'arm':arm,'task':task,'root':str(root),'trial':str(trial),'reward':row['result'].get('reward')}
 if arm=='native-kz':
  p=live/'trace/events.jsonl';events=[];counts=collections.Counter();config=None
  for n,s in enumerate(p.open(),1):
   e=json.loads(s);name=e.get('event');counts[name]+=1
   if name=='header':config=e.get('config')
   if name in ['tool_call','execution_assessment','error_route_execution_defect','error_route_admission','error_route_local_end','action_loop_block','contrastive_episode_start','contrastive_validation','critic_review','advisor_trigger','recovery_progress']:
    events.append({'line':n,**{k:v for k,v in e.items() if k not in ['sha256','previous']}})
  memory=live/'trace/exploration-memory.json'
  item.update(events=events,counts=dict(counts),config=config,failures=json.loads(memory.read_text()) if memory.exists() else [])
 else:
  p=next((live/'kz').glob('*.json'));state=json.loads(p.read_text())
  item.update(state=state.get('state'),config=state.get('config'),evidence=state.get('full',{}).get('evidence'))
  p=p.with_suffix('.jsonl');events=[];counts=collections.Counter()
  for n,s in enumerate(p.open(),1):
   e=json.loads(s);name=e.get('event');counts[name]+=1
   if name in ['created','outcome','gate','proposal','tool_admitted','tool_not_executed','native_outcome','background_outcome','completion_intent','critic_review','monitor_review','advisor_trigger']:
    events.append({'line':n,**e})
  item.update(events=events,counts=dict(counts))
 item['log']=str(p);item['log_sha256']=hashlib.sha256(p.read_bytes()).hexdigest();out['rows'].append(item)
 for rel in (['runtime/kz/src/policy.mjs','runtime/kz/src/full-task.mjs','runtime/kz/src/full-integration.mjs','runtime/kz/src/workspace.mjs'] if arm=='kz-dsh' else ['native/legacy/sources/bestfgs-project/src/bestfgs/lean_runtime.py','native/legacy/sources/bestfgs-project/src/bestfgs/contrastive_exploration.py','native/legacy/sources/bestfgs-project/src/bestfgs/error_routing.py']):
  path=root/rel
  if str(path) not in out['sources'] and path.exists():out['sources'][str(path)]={'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'text':path.read_text()}
print(json.dumps(out,ensure_ascii=False))
