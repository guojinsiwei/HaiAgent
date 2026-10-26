"""Real CPU desktop + actual multimodal API, sequential visible GUI state changes."""
import argparse,ast,base64,importlib.util,io,json,os,sys,time
from PIL import Image
from environment import ROOT,make_environment
from grading_cache import prepare_cache
spec=importlib.util.spec_from_file_location('repair_common',ROOT/'common.py');common=importlib.util.module_from_spec(spec);spec.loader.exec_module(common)
sys.path.insert(0,str(common.SOURCE))
from python.suz_agent import SUZAgent
os.environ['SUZ_API_KEY']=(ROOT/'secrets/api-key').read_text().strip()
folder=ROOT/'preflight-multistep';folder.mkdir(exist_ok=True)
html='''<!doctype html><html><body style="font:30px sans-serif;background:#fafafa;margin:80px"><h1>GUI compatibility preflight</h1><div id="box"></div><script>
let n=0; const codes=['ALPHA','BRAVO'];
function render(){if(n===2){document.body.style.background='#00cc55';box.innerHTML='<h1>All two steps verified</h1><h2>Completed successfully</h2>';return;}
box.innerHTML='<h2>Step '+(n+1)+' of 2</h2><p>Enter '+codes[n]+' below, then press Continue.</p><input id="entry" style="font-size:30px;width:450px" autocomplete="off"><br><br><button style="font-size:30px;padding:20px" onclick="advance()">Continue</button><p id="error"></p>';}
function advance(){if(entry.value===codes[n]){n++;render()}else{error.textContent='Please enter the displayed code exactly';}}render();</script></body></html>'''
rows=[]
parser=argparse.ArgumentParser();parser.add_argument('--mode',choices=['opencua_baseline','suz']);args=parser.parse_args()
for mode in ([args.mode] if args.mode else ['opencua_baseline','suz']):
    directory=folder/mode
    if (directory/'result.json').exists():
        row=json.loads((directory/'result.json').read_text());assert row['passed'];rows.append(row);continue
    directory.mkdir(exist_ok=True);env=None;agent=None
    try:
        task=json.loads((ROOT/'tasks/os/a4d98375-215b-4a4d-aee9-3d4370fccc41.json').read_text())
        cache=prepare_cache(ROOT/'assets',directory/('evaluation-cache-'+str(time.time_ns())),task['id'])
        env=make_environment(cache)
        env.reset(task_config=task)
        host=env.provider.container.attrs['HostConfig']
        assert host['Runtime']=='runc' and not host.get('DeviceRequests')
        assert all('nvidia' not in str(d).lower() and '/dev/dri' not in str(d).lower() for d in host.get('Devices',[]))
        code="import base64;open('/tmp/suz-preflight.html','wb').write(base64.b64decode("+repr(base64.b64encode(html.encode()).decode())+"))"
        env.setup_controller.setup([{'type':'execute','parameters':{'command':['python3','-c',code]}},
          {'type':'launch','parameters':{'command':['google-chrome','--no-sandbox','--new-window','--app=file:///tmp/suz-preflight.html']}},
          {'type':'sleep','parameters':{'seconds':3}}],False)
        obs,_,_,_=env.step("pyautogui.hotkey('alt','F10')",pause=2)
        agent=SUZAgent(common.config('multistep-repair4',mode,'preflight-repair4'),directory,node=str(ROOT/'.venv/bin/node'))
        instruction='Complete both steps in the GUI compatibility preflight window by entering each displayed code and pressing Continue. Use one visible UI interaction per turn and inspect the next screenshot. Finish when the green page says All two steps verified.'
        batches=0;primitive_actions=0
        for step in range(24):
            _,actions,info=agent.predict(instruction,{'screenshot':obs['screenshot']},step_idx=step)
            if actions in (['FAIL'],['DONE']):break
            for action in actions:
                obs,_,_,_=env.step(action,pause=1)
                agent.record_feedback('unknown','desktop returned screenshot')
                if action not in {'WAIT','DONE','FAIL'}:
                    primitive_actions+=sum(isinstance(n,ast.Call) for n in ast.walk(ast.parse(action)))
            batches+=1
            (directory/'last-observation.png').write_bytes(obs['screenshot'])
        with Image.open(io.BytesIO(obs['screenshot'])) as im:
            pixels=list(im.convert('RGB').resize((96,54)).getdata())
            green=sum(g>130 and r<40 and 40<b<140 for r,g,b in pixels)/len(pixels)
        state=agent.bridge.call('snapshot')
        assert actions==['DONE'] and green>.15 and batches>=4 and primitive_actions>=6,(mode,info,green,batches,primitive_actions)
        if mode=='suz':
            assert state['contractReady'] and state['review']['accepted']
            assert state['completionAudit']['decision']=='supported'
            assert sum(e['type']=='role_applied' and e.get('role')=='monitor' for e in state['events'])>=2
            # Expected defensive rejection may occur on a model's invalid citation.
            # It must not prevent verified task completion or weaken evidence checks.
            assert all(e['role']=='advisor' and e['reason']=='unknown or missing evidence IDs' for e in state['roleErrors']),state['roleErrors']
        row={'mode':mode,'passed':True,'cpu_only':True,'batches':batches,'primitive_actions':primitive_actions,'green_fraction':green,'verification':'Synthetic page turns green only after both exact code inputs; allow non-maximized window',
             'role_rejections':state['roleErrors'],'cost_cny':agent.client.spent,'requests':len(agent.client.calls),'source_sha256':common.source_hash(),'deployment_sha256':common.deployment_hash()}
        (directory/'result.json').write_text(json.dumps(row,indent=2));rows.append(row);print(json.dumps(row),flush=True)
    finally:
        if agent:agent.close()
        if env:env.close()
paths=[folder/m/'result.json' for m in ['opencua_baseline','suz']]
if all(p.exists() for p in paths):
    rows=[json.loads(p.read_text()) for p in paths]
    assert all(r['passed'] and r['deployment_sha256']==common.deployment_hash() for r in rows)
    (folder/'passed.json').write_text(json.dumps({'source_sha256':common.source_hash(),'deployment_sha256':common.deployment_hash(),'arms':rows,'timestamp':time.time()},indent=2))
