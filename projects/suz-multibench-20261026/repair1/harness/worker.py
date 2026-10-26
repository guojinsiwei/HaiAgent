"""One isolated official task; baseline and SUZ share this exact driver."""
import argparse,json,os,sys,time,hashlib
from pathlib import Path
from environments import WebEnvironment,AndroidEnvironment,boot_android

ANDROID_POLICY='''This environment is Android, overriding Ubuntu desktop assumptions. The Python syntax is a touch-action wire format. Use only pyautogui.click(x,y), doubleClick(x,y), write(text), scroll(n), hscroll(n), press('enter'), press('esc') for Android Back, press('home') for Android Home, hotkey('ctrl','a') before write to replace field text, or sleep(seconds). Positive vertical scroll moves toward the top; negative moves down. Coordinates are absolute pixels of the full phone screenshot. No desktop shortcuts, terminal, ADB, shell, DOM, accessibility tree, or developer tools. Open apps by visible launcher icons. Finish with computer.terminate(status='success' or 'fail').'''

def run():
    parser=argparse.ArgumentParser();parser.add_argument('--benchmark',choices=['webarena','androidworld'],required=True);parser.add_argument('--task',required=True);parser.add_argument('--mode',choices=['opencua_baseline','suz'],required=True);parser.add_argument('--preflight',action='store_true');args=parser.parse_args()
    root=Path('/campaign');directory=Path('/output');directory.mkdir(exist_ok=True)
    if (directory/'result.json').exists() or (directory/'cost-ledger.jsonl').exists():raise RuntimeError('Existing paid work must be preserved; refusing replay')
    spec=json.loads(Path(args.task).read_text());env=None;agent=None;emu=None
    status={'benchmark':args.benchmark,'mode':args.mode,'task_id':spec['id'],'stage':'setup','started':time.time()}
    def save():
        (directory/'worker-status.json').write_text(json.dumps(status,indent=2))
    save()
    try:
        if args.benchmark=='webarena':
            task=spec['task'];env=WebEnvironment(task,directory)
            instruction=task['intent']
        else:
            emu=boot_android(directory);env=AndroidEnvironment(spec,directory);instruction=spec['instruction']
        obs=env.reset();assert obs['screenshot'];(directory/'initial.png').write_bytes(obs['screenshot'])
        if args.preflight:
            transport=env.transport_preflight()
            score=env.evaluate();assert 0<=score<=1
            (directory/'result.json').write_text(json.dumps({'preflight':True,'passed':True,'official_score':score,'model_calls':0,'cpu_only':True,'transport':transport}))
            status.update(stage='preflight_passed');return
        ready=json.loads((root/('ready-'+args.benchmark+'.json')).read_text());assert ready['passed']
        cfg=json.loads((root/'model-config.json').read_text());cfg.update(task_id=spec['id'],mode=args.mode,budget_cny=8,
          shared_budget={'path':'/accounting/budget.sqlite','bucket':args.benchmark+'/'+args.mode+'/'+spec['id'],'total_limit_cny':320,'bucket_limit_cny':8})
        if args.benchmark=='androidworld':cfg['max_steps']=spec['max_steps']
        os.environ['SUZ_API_KEY']=Path('/secret/api-key').read_text().strip()
        from python.suz_agent import SUZAgent
        from python.observation import fresh_observation
        agent=SUZAgent(cfg,directory,node='/usr/local/bin/node')
        if args.benchmark=='androidworld':agent.system_prompt+='\n'+ANDROID_POLICY
        (directory/'run-config.json').write_text(json.dumps(cfg,indent=2));status['stage']='running';save()
        result={'official_score':None,'error':None,'executed_batches':0,'started':time.time()}
        try:
            for step in range(agent.max_steps):
                _,actions,info=agent.predict(instruction,{'screenshot':obs['screenshot']},step_idx=step)
                result['agent_status']=info.get('suz_status')
                if actions in (['DONE'],['FAIL']):break
                if args.benchmark=='androidworld':
                    try:
                        for action in actions:
                            if action!='WAIT':env.actions.compile(action)
                    except ValueError as exc:
                        agent.record_feedback('failure','No action executed: '+str(exc));continue
                for action in actions:obs,_,_,_=env.step(action,pause=2)
                obs=fresh_observation(env,obs);agent.record_feedback('unknown','Fresh screenshot returned; task success unverified')
                result['executed_batches']+=1;(directory/'last-observation.png').write_bytes(obs['screenshot'])
        except Exception as exc:result['error']=type(exc).__name__+': '+str(exc)[:500]
        status['stage']='grading';save()
        try:result['official_score']=env.evaluate()
        except Exception as exc:result['grading_error']=type(exc).__name__+': '+str(exc)[:500]
        result.update(model_requests=len(agent.client.calls),accounted_cny=agent.client.spent,wall_seconds=time.time()-result['started'])
        (directory/'result.json').write_text(json.dumps(result,indent=2));status.update(stage='completed',outcome=result)
    except Exception as exc:status.update(stage='engineering_failure',error=type(exc).__name__+': '+str(exc)[:500])
    finally:
        for obj in [agent,env]:
            try:
                if obj:obj.close()
            except Exception as exc:status.setdefault('cleanup_errors',[]).append(type(exc).__name__+': '+str(exc)[:200])
        if emu:
            try:emu.terminate();emu.wait(timeout=30)
            except Exception:emu.kill()
        status['updated']=time.time();save()

if __name__=='__main__':run()
