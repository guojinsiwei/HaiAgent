from pathlib import Path
from collections import Counter
from datetime import datetime,timezone,timedelta
import json,re
root=Path(__file__).resolve().parent/'audit-20261024'
manifest=json.loads((root/'task-manifest.json').read_text())['tasks']
output={'groups':{},'comparisons':[],'time':{}}
for mode in ['opencua_baseline','suz']:
    aggregate={'finished':0,'passed':0,'cny':0,'seconds':0,'requests':0,'executed_batches':0,
        'stops':Counter(),'roles':Counter(),'role_errors':Counter(),'mechanisms':Counter(),'rows':[]}
    for row in manifest:
        folder=root/'runs'/mode/row['id']
        result=json.loads((folder/'result.json').read_text())
        controller=json.loads((folder/'controller.json').read_text())
        events=[json.loads(line) for line in (folder/'mechanisms.jsonl').read_text().splitlines()]
        calls={}
        for line in (folder/'cost-ledger.jsonl').read_text().splitlines():
            call=json.loads(line);calls[call['id']]=call
        for call in calls.values():aggregate['roles'][call['role']]+=1
        for error in controller['roleErrors']:aggregate['role_errors'][error['role']+': '+error['reason']]+=1
        for event in events:aggregate['mechanisms'][event.get('type',event.get('event','unknown'))]+=1
        batches=sum(e.get('type')=='transition' for e in events)
        aggregate['finished']+=1;aggregate['passed']+=result['official_score']==1
        aggregate['cny']+=result['total_accounted_cny'];aggregate['seconds']+=result['wall_seconds']
        aggregate['requests']+=result['model_requests'];aggregate['executed_batches']+=batches
        reason=result.get('agent_status') or 'unknown';aggregate['stops'][reason]+=1
        last=list(calls.values())[-1]
        aggregate['rows'].append({'id':row['id'],'domain':row['domain'],'instruction':row['instruction'],
            **result,'executed_batches':batches,'last_role':last['role'],
            'last_completion_tokens':last.get('usage',{}).get('completion_tokens'),
            'last_reasoning_tokens':last.get('usage',{}).get('completion_tokens_details',{}).get('reasoning_tokens'),
            'role_errors':controller['roleErrors'],'routes':len(controller['planner']['routes']),
            'switches':controller['planner']['switches'],'warnings':len(controller['visualWarnings']['items']),
            'memories':len(controller['memory']['items'])})
    output['groups'][mode]=aggregate
for index,row in enumerate(manifest):
    a=output['groups']['opencua_baseline']['rows'][index]['official_score']
    b=output['groups']['suz']['rows'][index]['official_score']
    if a or b:output['comparisons'].append({'id':row['id'],'instruction':row['instruction'],'baseline':a,'suz':b})
pair_states=[json.loads(p.read_text()) for p in (root/'pairs').glob('*/status.json')]
start=min(p['started'] for p in pair_states);end=float((root/'logs/queue.finished').read_text())
output['time']={'started_beijing':datetime.fromtimestamp(start,timezone(timedelta(hours=8))).isoformat(),
                'finished_beijing':datetime.fromtimestamp(end,timezone(timedelta(hours=8))).isoformat(),
                'elapsed_seconds':end-start}
pattern=r'Projecting coordinates: \(([^,]+), ([^)]+)\) to \((\d+), (\d+)\) using relative'
projections=[]
for path in (root/'logs').glob('pair-*.log'):
    for match in re.finditer(pattern,path.read_text(errors='replace')):
        x,y,xx,yy=map(float,match.groups())
        if xx>100000 or yy>100000:projections.append({'task':path.stem[5:],'input':[x,y],'projected':[xx,yy]})
output['overscaled_coordinates']=projections
(root/'analysis.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
compact={**output,'groups':{mode:{key:value for key,value in group.items() if key!='rows'} for mode,group in output['groups'].items()}}
compact['overscaled_coordinates']={'count':len(projections),'examples':projections[:3]}
print(json.dumps(compact,ensure_ascii=False,indent=2))
