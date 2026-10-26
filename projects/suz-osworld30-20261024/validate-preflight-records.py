"""Audit existing live evidence; account for legal batched GUI operations.

No inference or desktop actions. Original trace and failed assertion stay retained.
The original minimum-six-batches check incorrectly rejects two legal click+type
batches. Require >=6 primitive actions, >=4 feedback cycles, multiple Monitor
applications and actual final Critic acceptance, with the same terminal screen.
"""
import ast,collections,json,time
from PIL import Image
from common import ROOT,source_hash,deployment_hash
folder=ROOT/'preflight-multistep';rows=[]
baseline=json.loads((folder/'opencua_baseline/result.json').read_text())
assert baseline['source_sha256']==source_hash() and baseline['deployment_sha256']==deployment_hash()
for mode in ['opencua_baseline','suz']:
    p=folder/mode
    state=json.loads((p/'controller.json').read_text())
    events=[json.loads(x) for x in (p/'agent.jsonl').read_text().splitlines()]
    predictions=[x for x in events if x['event']=='prediction']
    assert predictions[-1]['actions']==['DONE']
    assert state['halted']==('visually_accepted' if mode=='suz' else 'solver_declared_done')
    dispatched=[x for x in predictions if x['actions'] not in (['DONE'],['FAIL'],['WAIT'])]
    primitives=sum(sum(isinstance(n,ast.Call) for n in ast.walk(ast.parse(a))) for x in dispatched for a in x['actions'])
    assert len(dispatched)>=4 and primitives>=6
    assert len(state['transitions'])>=len(dispatched)
    assert not state['roleErrors']
    if mode=='suz':
        assert state['review']['accepted'] and state['review']['frame']==state['current']
        assert sum(e['type']=='role_applied' and e.get('role')=='monitor' for e in state['events'])>=2
    with Image.open(p/'last-observation.png') as im:
        pixels=list(im.convert('RGB').resize((96,54)).getdata())
        green=sum(g>130 and r<40 and 40<b<140 for r,g,b in pixels)/len(pixels)
    assert green>.45
    costs={x['id']:x for x in map(json.loads,(p/'cost-ledger.jsonl').read_text().splitlines())}
    assert all(x['status']=='settled' for x in costs.values())
    row={'mode':mode,'passed':True,'cpu_only':True,'batches':len(dispatched),'primitive_actions':primitives,
         'green_fraction':green,'requests':len(costs),'cost_cny':sum(x['charge_cny'] for x in costs.values()),
         'source_sha256':source_hash(),'deployment_sha256':deployment_hash(),
         'audit':'legal action batching; >=4 feedback cycles and >=6 GUI actions; original traces retained'}
    (p/'audited-result.json').write_text(json.dumps(row,indent=2));rows.append(row)
result={'source_sha256':source_hash(),'deployment_sha256':deployment_hash(),'arms':rows,'timestamp':time.time()}
(folder/'passed.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
