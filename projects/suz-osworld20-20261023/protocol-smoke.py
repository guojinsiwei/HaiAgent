"""Check real GLM role JSON and official action parsing on a synthetic UI."""
import json
import os
import sys
from pathlib import Path
from PIL import Image,ImageDraw
from environment import ROOT
sys.path.insert(0,str(ROOT/'SUZ'))
from python.suz_agent import SUZAgent
from python.actions import click_points

os.environ['SUZ_API_KEY']=(ROOT/'secrets/api-key').read_text().strip()
config=json.loads((ROOT/'model-config.json').read_text())
config.update(external_vlm_adapter=True,coordinate_type='relative',max_output_tokens=8192,role_max_tokens=8192)
config.pop('request_extra',None)
(ROOT/'model-config.json').write_text(json.dumps(config,indent=2))
folder=ROOT/'preflight-protocol-v4';folder.mkdir(exist_ok=True)
image=Image.new('RGB',(560,560),'#eeeeee');draw=ImageDraw.Draw(image)
draw.rectangle((50,50,510,510),fill='white',outline='black',width=2)
draw.text((100,110),'Test window',fill='black',font_size=30)
draw.rectangle((180,280,380,360),fill='#1764c0')
draw.text((235,300),'Save',fill='white',font_size=26)
image.save(folder/'fixture.png')
results=[]
for mode in ['opencua_baseline','suz']:
    directory=folder/mode
    cfg={**config,'task_id':'synthetic-save-probe','mode':mode,'budget_cny':1,
         'shared_budget':{'path':str(ROOT/'budget.sqlite'),'bucket':'preflight-compatibility',
                          'total_limit_cny':320,'bucket_limit_cny':1}}
    agent=SUZAgent(cfg,directory,node=str(ROOT/'.venv/bin/node'))
    try:
        _,actions,info=agent.predict('Click the blue Save button once.',{'screenshot':(folder/'fixture.png').read_bytes()},step_idx=0)
        points=click_points(actions,(560,560))
        passed=any(180/560<=p['x']<=380/560 and 280/560<=p['y']<=360/560 for p in points)
        if mode=='suz':
            events=[json.loads(line) for line in (directory/'mechanisms.jsonl').read_text().splitlines()]
            state=json.loads((directory/'controller.json').read_text())
            if state.get('roleErrors') or not state.get('contractReady'):passed=False
        results.append({'mode':mode,'passed':passed,'actions':actions,'status':info.get('suz_status'),
                        'cost_cny':agent.client.spent,'model_requests':len(agent.client.calls)})
        if not passed:raise RuntimeError('Protocol or grounding preflight failed: '+mode)
    finally:agent.close()
(folder/'result.json').write_text(json.dumps(results,indent=2))
print(json.dumps(results),flush=True)
(ROOT/'logs/protocol.ready').write_text('passed\n')
