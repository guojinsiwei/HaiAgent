"""Read-only mechanism audit of finished valid trials; emits JSON to stdout."""
import collections,json,pathlib,datetime
B=pathlib.Path('/mnt/sdb/home/lizh639')
NAMES=['tb2-three-arm50-20261017','tb2-three-arm50-retry-20261018','tb2-three-arm50-retry2-20261018','tb2-three-arm50-boost6-20261018','tb2-three-arm50-scorefix-20261018']
merged={}
for name in NAMES:
 p=B/name/'health.json'
 if not p.exists():continue
 for r in json.loads(p.read_text()).get('rows',[]):
  if r.get('engineering_clean') and r.get('state')=='done':merged[r.get('budget_job',r['job'])]={**r,'campaign':name}
out={'snapshot_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'rows':[]}
for r in merged.values():
 arm=r['arm'];p=pathlib.Path(r['result']['trial'])/'agent/live'
 d={k:r.get(k) for k in ['arm','task','job','campaign']};d.update(trial=str(p.parent),reward=r['result'].get('reward'),requests=r['result'].get('requests'),tools=r['result'].get('tools'),budget=r['result'].get('budget_exhausted'))
 if arm=='dsh':out['rows'].append(d);continue
 fs=[p/'trace/events.jsonl'] if arm=='native-kz' else list((p/'kz').glob('*.jsonl'))
 counts=collections.Counter();metrics=collections.Counter();details=[]
 for f in fs:
  for lineno,s in enumerate(f.read_text().splitlines(),1):
   try:e=json.loads(s)
   except:continue
   k=e.get('event','?');counts[k]+=1
   if k=='memory_retrieval':
    metrics['retrieval_nonempty']+=bool(e.get('selected_ids'));metrics['retrieved_items']+=len(e.get('selected_ids',[]));metrics['reserve_omitted']+=len(e.get('reserve_omitted_ids',[]))
   if k=='memory_followup_outcome':
    for field in ['process_succeeded','changed','workspace_changed','clean_check','action_changed']:
     metrics['memory_'+field]+=e.get(field) is True
    metrics['memory_check_'+str(e.get('check_status'))]+=1
   if k=='model_request':metrics['role_'+str(e.get('role'))]+=1
   if k=='role_request':metrics['role_'+str(e.get('role'))]+=1
   if k=='gate':metrics['gate_'+str(e.get('decision',{}).get('reason'))]+=1
   if k=='monitor_review':metrics['monitor_'+str(e.get('verdict',e.get('review',{}).get('verdict')))]+=1
   if k=='memory_decision_review':metrics['memory_decision_'+str(e.get('review',{}).get('decision'))]+=1
   if k=='critic_review':metrics['critic_accepted_'+str(e.get('accepted'))]+=1
   if k=='critic_plan_needs_followup':
    for err in e.get('preflight',{}).get('errors',[]):metrics['critic_preflight_'+err]+=1
   if k in ['monitor_deferred','advisor_deferred','monitor_unavailable','critic_unavailable','critic_review_unavailable']:
    metrics[k+'_'+str(e.get('detail',e.get('reason',e.get('error',e.get('error_type')))))]+=1
   if k in ['critic_review','submission','advisor_trigger','advice','advisor_response','exploration_learning','contrastive_episode_start','contrastive_validation','contrastive_outcome','action_loop_block','monitor_review','completion_blockage_diagnosis','completion_review','critic_plan_needs_followup']:
    v={a:b for a,b in e.items() if a not in ['previous','sha256','session','commitSeq','hostSeq']}
    # Preserve selected evidence and decisions without huge duplicate state.
    if 'completion' in v:v['completion']={a:v['completion'].get(a) for a in ['status','gaps']}
    details.append({'file':str(f),'line':lineno,'event':v})
 d.update(events=dict(counts),metrics=dict(metrics),details=details)
 if arm=='native-kz':
  for name in ['exploration-trigger','exploration-memory','exploration-results']:
   f=p/'trace'/f'{name}.json'
   if f.exists():
    v=json.loads(f.read_text())
    d[name]=v if name!='exploration-memory' else [{k:x.get(k) for k in ['id','evidence_id','check_key','goal','observation']} for x in v]
  d['usage']=r['result'].get('usage')
 else:
  for f in (p/'kz').glob('*.json'):
   st=json.loads(f.read_text());s=st['state'];full=st['full']
   d['policy']={k:s.get(k) for k in ['active','counters','episode','trigger','experiments']}
   d['full']={k:full.get(k) for k in ['memory','memoryEffects','advisory','completion','critic','subgoals']}
 out['rows'].append(d)
import gzip,base64
print(base64.b64encode(gzip.compress(json.dumps(out,ensure_ascii=False).encode())).decode())
