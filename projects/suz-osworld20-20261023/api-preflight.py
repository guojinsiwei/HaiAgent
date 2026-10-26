"""One small image call. Entire request is charged to the shared experiment cap."""
from pathlib import Path
import base64
import io
import json
import os
import sys

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'SUZ'))
from PIL import Image, ImageDraw
from python.runtime import MeteredClient, parse_json

cfg=json.loads((ROOT/'SUZ/config/example.json').read_text())
cfg.update(allow_live=True,base_url='https://api.taotoken.net/token/v1',
           solver_model='glm-5.3-flash',role_model='glm-5.3-flash',
           input_cny_per_million=0.8,output_cny_per_million=2.8,
           max_input_tokens=1000000,max_output_tokens=4096,role_max_tokens=4096,
           budget_cny=8,max_requests=400,request_timeout=180,
           server_gpu_allowed=False,
           provider_contract={'model':'glm-5.3-flash','base_url':'https://api.taotoken.net/token/v1',
               'max_context_tokens':1000000,'source_url':'https://taotoken.net/models?modelId=glm-5.3-flash'},
           pricing_basis='TaoToken published uncached token tariff equivalent; Token Plan credits may differ')
cfg['shared_budget']={'path':str(ROOT/'budget.sqlite'),'bucket':'preflight-compatibility','total_limit_cny':320,'bucket_limit_cny':1}
cfg['budget_cny']=1
folder=ROOT/'preflight-api-compatibility';folder.mkdir(exist_ok=True)
os.environ['SUZ_API_KEY']=(ROOT/'secrets/api-key').read_text().strip()
client=MeteredClient(cfg,folder)
canvas=Image.new('RGB',(560,560),'white')
draw=ImageDraw.Draw(canvas)
draw.rectangle((110,200,450,350),fill='red')
draw.text((165,250),'SUZ 6427',fill='white',font_size=38)
buf=io.BytesIO();canvas.save(buf,format='PNG')
(folder/'fixture.png').write_bytes(buf.getvalue())
payload={'model':'glm-5.3-flash','temperature':0,'max_tokens':512,
 'messages':[{'role':'user','content':[
 {'type':'text','text':'Read the image. Return only JSON with label (exact text in the rectangle) and button_color (English color name).'},
 {'type':'image_url','image_url':{'url':'data:image/png;base64,'+base64.b64encode(buf.getvalue()).decode()}}]}]}
output=client.complete('vision_preflight',payload)
result=parse_json(output)
passed=result.get('label')=='SUZ 6427' and str(result.get('button_color','')).lower()=='red'
record={'image_input_passed':passed,'response':result,'cost_cny':client.spent,'requests':len(client.calls)}
(folder/'result.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
print(json.dumps(record))
if not passed:raise RuntimeError('Vision fixture failed; experiment must not start')
cfg.update(budget_cny=8)
cfg.pop('shared_budget')
cfg['external_vlm_adapter']=True
cfg['coordinate_type']='relative'
(ROOT/'model-config.json').write_text(json.dumps(cfg,indent=2),encoding='utf-8')
