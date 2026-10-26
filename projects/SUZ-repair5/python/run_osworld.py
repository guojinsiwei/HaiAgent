"""Single-task runner. Task setup/grading stay outside every model context."""
import argparse
import hashlib
import json
from pathlib import Path
import time
from .outcomes import classify
from .observation import fresh_observation


def run_task(agent, env, task, directory):
    directory=Path(directory)
    started=time.time()
    outcome={'task_id':task['id'],'official_score':None,'error':None,'executed_batches':0,'phase':'setup'}
    try:
        obs=env.reset(task_config=task)
        outcome['phase']='solving'
        for step in range(agent.max_steps):
            _,actions,info=agent.predict(task['instruction'],{'screenshot':obs['screenshot']},step_idx=step)
            outcome['agent_status']=info.get('suz_status')
            # FAIL/DONE are harness sentinels, not GUI code. Evaluate the preserved VM below.
            if actions in (['FAIL'],['DONE']):
                # Official infeasible grading depends on an intentional FAIL in history.
                # Budget/transport/parser stops must never be converted to that verdict.
                if actions==['DONE'] or info.get('suz_status')=='solver_declared_fail':
                    obs,_,_,_=env.step(actions[0],pause=0)
                break
            done=False
            for action in actions:
                obs, _reward, done, _info=env.step(action,pause=2)
                # env.step can mask execution exceptions; never infer successful execution.
                agent.record_feedback('unknown','Environment returned a screenshot; execution success unverified')
                if done:break
            obs=fresh_observation(env,obs)
            (directory/'last-observation.png').write_bytes(obs['screenshot'])
            outcome['executed_batches']+=1
            if done:break
        # Called once after solving. Score is never returned to the agent/controller.
        outcome['phase']='grading'
        outcome['official_score']=env.evaluate()
        outcome['phase']='graded'
    except Exception as exc:
        outcome['error']=type(exc).__name__+': '+str(exc)[:400]
        # Preserve solver error, but try official grading of the existing state.
        if outcome['phase']=='solving':
            try:
                outcome['official_score']=env.evaluate()
                outcome['recovered_grading']=True
            except Exception as grading_exc:
                outcome['grading_error']=type(grading_exc).__name__+': '+str(grading_exc)[:300]
    finally:
        outcome['wall_seconds']=time.time()-started
        outcome['total_accounted_cny']=agent.client.spent
        outcome['model_requests']=len(agent.client.calls)
        outcome['outcome_kind']=classify(outcome)
        (directory/'result.json').write_text(json.dumps(outcome,indent=2),encoding='utf-8')
        agent.close()
    return outcome


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--task',required=True);parser.add_argument('--config',required=True)
    parser.add_argument('--run-dir',required=True);parser.add_argument('--vm-path',required=True)
    parser.add_argument('--provider',choices=['vmware','virtualbox','docker'],default='docker')
    parser.add_argument('--node',default='node')
    args=parser.parse_args()
    cfg=json.loads(Path(args.config).read_text(encoding='utf-8'))
    if cfg.get('allow_live') is not True or cfg.get('budget_cny',0)<=0:
        parser.error('configure explicit live authorization and independent per-task budget first')
    directory=Path(args.run_dir)
    if directory.exists() and any(directory.iterdir()):parser.error('run directory must be empty')
    directory.mkdir(parents=True,exist_ok=True)
    task=json.loads(Path(args.task).read_text(encoding='utf-8'))
    cfg['task_id']=task['id']
    (directory/'run-config.json').write_text(json.dumps(cfg,indent=2),encoding='utf-8')
    (directory/'task-sha256.txt').write_text(hashlib.sha256(Path(args.task).read_bytes()).hexdigest())
    from .suz_agent import SUZAgent
    from desktop_env.desktop_env import DesktopEnv
    agent=SUZAgent(cfg,directory,node=args.node)
    env=None
    try:
        env=DesktopEnv(provider_name=args.provider,path_to_vm=args.vm_path,action_space='pyautogui',
                       require_a11y_tree=False,require_terminal=False,headless=True)
        print(json.dumps(run_task(agent,env,task,directory),ensure_ascii=False))
    finally:
        agent.close()
        if env is not None:env.close()


if __name__=='__main__':main()
