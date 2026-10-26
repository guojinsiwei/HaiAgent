"""One bounded Critic-only check of stored raw screenshots; no GUI or grading hints."""
import base64,json,os,sys
from pathlib import Path
from common import ROOT,SOURCE,config
sys.path.insert(0,str(SOURCE))
from python.runtime import ControllerBridge,MeteredClient,parse_json
task_id='2cd43775-7085-45d8-89fa-9e35c0a915cf'
old=ROOT.parent/'runs/suz'/task_id
row=next(r for r in json.loads((ROOT/'task-manifest.json').read_text())['tasks'] if r['id']==task_id)
task=json.loads((ROOT/row['path']).read_text())
state=json.loads((old/'controller.json').read_text())
directory=ROOT/'semantic-replay'/task_id;directory.mkdir(parents=True,exist_ok=False)
cfg=config(task_id,'suz');(directory/'run-config.json').write_text(json.dumps(cfg,indent=2))
os.environ['SUZ_API_KEY']=(ROOT/'secrets/api-key').read_text().strip()
bridge=ControllerBridge(directory,task_id,task['instruction'],cfg,node=str(ROOT/'.venv/bin/node'))
client=MeteredClient(cfg,directory)
try:
    ids=['F0',state['current']]
    for fid in ids:bridge.call('observe',value={'base64':base64.b64encode((old/'frames'/f'{fid}.png').read_bytes()).decode()})
    context=bridge.call('context',role='critic',stage='audit')
    content=[{'type':'text','text':json.dumps(context['payload'])}]
    for image in context['images']:
        content.extend([{'type':'text','text':'Screenshot '+image['id']},{'type':'image_url','image_url':{'url':image['dataUrl']}}])
    output=client.complete('critic',{'model':cfg['role_model'],'temperature':0,'max_tokens':cfg['role_max_tokens'],
        'messages':[{'role':'system','content':context['system']},{'role':'user','content':content}]})
    verdict=parse_json(output);bridge.call('apply',role='critic',stage='audit',value=verdict)
    result={'original_frames':ids,'audit':verdict,'cost_cny':client.spent,'model_requests':len(client.calls),
        'official_score_unchanged':True,'executed_actions':0}
    (directory/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
finally:bridge.close()
