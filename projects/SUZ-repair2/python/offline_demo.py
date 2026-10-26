"""Deterministic wiring demonstration, NOT a visual-capability evaluation."""
import argparse
import io
import json
from pathlib import Path
from unittest.mock import patch
from PIL import Image, ImageDraw
from .runtime import MeteredClient
from .suz_agent import SUZAgent


def run(directory):
    directory=Path(directory)
    if directory.exists() and any(directory.iterdir()):raise ValueError('demo output must be a fresh directory')
    directory.mkdir(parents=True,exist_ok=True)
    config=json.loads((Path(__file__).resolve().parents[1]/'config/example.json').read_text())
    config.update(task_id='offline-save-workflow',budget_cny=1,input_cny_per_million=2,output_cny_per_million=4,monitor_every=1)
    state={'solvers':0,'planners':0,'roles':[],'overlay_messages':0,'crop_messages':0}
    instruction='Save the document as report.txt'

    def respond(payload):
        system=payload['messages'][0]['content']
        first=payload['messages'][-1]['content'][0]
        # Native OpenCUA starts the final user message with an image; role messages start with JSON.
        context=json.loads(first['text']) if first.get('type')=='text' else None
        if 'stage=plan' in system:
            role='critic'
            if context['stage']=='plan':value={'obligations':[{'id':'G1','quote':'report.txt','predicate':'saved file named report.txt'}]}
            else:value={'decision':'accept','assessments':[{'id':o['id'],'status':'met','frame_ids':[context['frame_id']],
                'basis':'visible_result','reason':'scripted fixture shows saved filename'} for o in context['obligations']]}
        elif 'BEFORE and AFTER' in system:
            role='monitor';ids=list(context['evidence']);stalled=len(ids)>=2 and state['solvers']<3
            value={'verdict':'stalled' if stalled else 'uncertain','reason':'scripted unchanged editor fixture',
                   'evidence_ids':ids[-2:] if stalled else ids[-1:],'memories':[
                     {'kind':'blocker','conclusion':'Save button did not open dialog','condition':'unchanged editor screenshot',
                      'operation':'Save document','next_step':'try menu workflow','evidence_ids':ids[-1:]}] if stalled else []}
        elif 'Diagnose the current local difficulty' in system:
            role='advisor';value={'alternatives':[{'hypothesis':'save icon is inactive','check':'open File menu',
                'difference':'use menu command','evidence_ids':list(context['evidence'])[-2:]}],
                'visual_warnings':[{'frame_id':context['frame_id'],'target':'toolbar Save button',
                  'box':[.38,.20,.62,.30],'condition':'Untitled editor, grey inactive Save button',
                  'diagnosis':'two clicks did not open a dialog; fixture shows disabled button','cause':'disabled',
                  'confidence':.9,'evidence_ids':list(context['evidence'])[-2:]}]}
        elif 'semantic direction planner' in system:
            role='planner';state['planners']+=1;later=state['planners']>1;ids=list(context['evidence'])[-2:]
            mechanism='File menu Save As' if later else 'toolbar Save'
            value={'task_model':{'problem':instruction,'environment':'editor','unknowns':[]},
                'new_routes':[{'id':'N1','hypothesis':mechanism,'mechanism':mechanism,'target':'editor',
                  'steps':['open '+mechanism,'save file and inspect visible result'],'progress_signal':'saved filename',
                  'abandon_when':'no dialog','evidence_ids':ids}],
                'evaluations':[{'route_id':r['id'],'suitability':0.1,'disposition':'retain','reason':'unchanged screen','evidence_ids':ids}
                  for r in context['retained_routes']]+[{'route_id':'N1','suitability':0.9,'disposition':'retain','reason':'available path','evidence_ids':ids}],
                'reason':'change workflow after failed clicks','evidence_ids':ids,'contrast':{'dimension':'mechanism','reason':'toolbar to menu'}}
            if context['memory']:value['memory_review']={'ids':[m['id'] for m in context['memory']],
                'decision':'different_route','observed_result':'toolbar unchanged','applicability':'same editor; recheck dialog state',
                'reason':'avoid repeating ineffective toolbar click'}
        else:
            role='solver';state['solvers']+=1
            action='pyautogui.click(x=280, y=140)' if state['solvers']<3 else (
                'pyautogui.click(x=28, y=28)' if state['solvers']==3 else 'computer.terminate(status="success")')
            value='## Observation\nEditor\n## Thought\nFollow route\n## Action\nSave document\n```python\n'+action+'\n```'
        derived=[json.loads(c['text']) for m in payload['messages'] if isinstance(m['content'],list)
                 for c in m['content'] if c.get('type')=='text' and c.get('text','').startswith('{"kind":')]
        if role=='solver':state['overlay_messages']+=sum(d.get('kind')=='derived_warning_overlay' for d in derived)
        if role=='advisor':state['crop_messages']+=sum(d.get('kind')=='diagnostic_crop' for d in derived)
        if role in {'critic','monitor'}:assert not derived
        state['roles'].append(role)
        return {'choices':[{'finish_reason':'stop','message':{'content':value if isinstance(value,str) else json.dumps(value)}}],
                'usage':{'prompt_tokens':100,'completion_tokens':50}}

    agent=SUZAgent(config,directory,client=MeteredClient(config,directory,sender=respond))
    actions=[]
    try:
        with patch('urllib.request.urlopen',side_effect=AssertionError('offline demo cannot access model network')):
            for i in range(4):
                image=Image.new('RGB',(560,560),'#f6f7fb');draw=ImageDraw.Draw(image)
                draw.rectangle((0,0,560,50),fill='#e3e8f0')
                draw.text((20,20),'File    Edit    View',fill='black')
                draw.text((20,80),'report.txt - Saved' if i==3 else 'Untitled - Unsaved',fill='black')
                draw.rounded_rectangle((213,112,347,168),radius=7,fill='#d4d7dd',outline='#b7bec8')
                draw.text((266,134),'Save',fill='#8b9098')
                draw.rectangle((25,195,535,500),fill='white',outline='#d8dce5')
                draw.text((42,220),'Experiment notes',fill='#364152')
                draw.text((42,245),'A synthetic desktop fixture for offline testing.',fill='#586474')
                buf=io.BytesIO();image.save(buf,format='PNG')
                _,action,_=agent.predict(instruction,{'screenshot':buf.getvalue()})
                actions.append(action);agent.record_feedback('unknown','synthetic environment observation')
            snapshot=agent.bridge.call('snapshot')
            summary={'mode':'scripted offline integration; no visual capability claim','live_model_calls':0,
                'real_spend_cny':0,'scripted_requests':len(state['roles']),'role_counts':{r:state['roles'].count(r) for r in set(state['roles'])},
                'route_switches':snapshot['planner']['switches'],'memory_items':len(snapshot['memory']['items']),
                'memory_route_bindings':len(snapshot['memoryEffects']),'final_actions':actions[-1],
                'visual_warnings':len(snapshot.get('visualWarnings',{}).get('items',[])),
                'solver_overlay_messages':state['overlay_messages'],'advisor_crop_messages':state['crop_messages'],
                'overlay_files':[str(p.relative_to(directory)) for p in (directory/'derived-views').glob('solver-*.png')],
                'official_score':None,'actions':actions}
            assert summary['route_switches']>=1 and summary['memory_route_bindings']>=1
            assert set(summary['role_counts'])=={'planner','solver','monitor','advisor','critic'}
            assert actions[-1]==['DONE']
            assert summary['visual_warnings']==1 and len(summary['overlay_files'])==1
            assert state['overlay_messages']==1 and state['crop_messages']==2
            (directory/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
            return summary
    finally:agent.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True)
    print(json.dumps(run(parser.parse_args().output),ensure_ascii=False,indent=2))
