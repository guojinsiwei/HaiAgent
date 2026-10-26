import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image

from python.runtime import MeteredClient, RunStop
from python.actions import validate_actions
from python.suz_agent import SUZAgent


def configuration():
    value=json.loads(Path('config/example.json').read_text())
    value.update(task_id='test',budget_cny=8,input_cny_per_million=2,output_cny_per_million=4)
    return value


def response(content='ok', **kwargs):
    return {'choices':[{'finish_reason':'stop','message':{'content':content}}],
            'usage':{'prompt_tokens':100,'completion_tokens':20},**kwargs}


class BudgetTests(unittest.TestCase):
    def test_all_roles_charged_and_restart_cannot_reset_budget(self):
        with tempfile.TemporaryDirectory() as folder:
            cfg=configuration();cfg['max_requests']=5
            client=MeteredClient(cfg,folder,sender=lambda _:response())
            for role in ['solver','planner','monitor','advisor','critic']:
                client.complete(role,{'max_tokens':100})
            self.assertAlmostEqual(client.spent,5*0.00028)
            recovered=MeteredClient(cfg,folder,sender=lambda _:self.fail('should not send'))
            with self.assertRaises(RunStop):recovered.complete('solver',{})
            self.assertEqual({x['role'] for x in recovered.calls.values()},{'solver','planner','monitor','advisor','critic'})

    def test_unknown_transport_keeps_reservation(self):
        with tempfile.TemporaryDirectory() as folder:
            def fail(_):raise RunStop('timeout')
            client=MeteredClient(configuration(),folder,sender=fail)
            with self.assertRaises(RunStop):client.complete('critic',{})
            self.assertGreater(client.spent,0)
            self.assertEqual(client.calls[1]['status'],'reserved')

    def test_insufficient_budget_and_disabled_live_call_send_nothing(self):
        with tempfile.TemporaryDirectory() as folder:
            cfg=configuration();cfg['budget_cny']=0.00001
            client=MeteredClient(cfg,folder,sender=lambda _:self.fail('called'))
            with self.assertRaises(RunStop):client.complete('solver',{})
            self.assertEqual(len(client.calls),0)
            cfg['budget_cny']=8
            client=MeteredClient(cfg,folder)
            with self.assertRaises(RunStop):client.complete('solver',{})

    def test_truncated_output_is_charged_once_and_not_retried(self):
        with tempfile.TemporaryDirectory() as folder:
            client=MeteredClient(configuration(),folder,sender=lambda _:response(choices=[{'finish_reason':'length'}]))
            with self.assertRaises(RunStop):client.complete('solver',{})
            self.assertEqual(len(client.calls),1)
            self.assertEqual(client.calls[1]['status'],'settled')

    def test_live_requires_verified_server_context_bound(self):
        with tempfile.TemporaryDirectory() as folder:
            cfg=configuration();cfg['allow_live']=True
            requests=[]
            def fake_urlopen(request,**kwargs):
                requests.append(request.full_url)
                return io.BytesIO(json.dumps({'data':[{'id':'opencua-7b','max_model_len':999999}]}).encode())
            client=MeteredClient(cfg,folder)
            with patch('urllib.request.urlopen',side_effect=fake_urlopen):
                with self.assertRaises(RunStop):client.complete('solver',{'model':'opencua-7b'})
            self.assertTrue(all(url.endswith('/models') for url in requests))


class ActionTests(unittest.TestCase):
    def test_no_host_or_shell_code(self):
        for code in ['import os; os.system("ls")','exec("x")','pyautogui.click(x=get_x(),y=1)',
                     'while True: pyautogui.click(1,2)','time.sleep(3600)','pyautogui.click(**args)']:
            with self.assertRaises((ValueError,TypeError)):validate_actions([code])
        self.assertEqual(validate_actions(['import pyautogui\npyautogui.click(20, 30)']),['import pyautogui\npyautogui.click(20, 30)'])


class IntegrationTests(unittest.TestCase):
    def test_grading_is_once_and_hidden_data_never_enters_agent(self):
        from python.run_osworld import run_task
        class FakeClient:
            spent=0
            calls={}
        class FakeAgent:
            max_steps=2
            client=FakeClient()
            def predict(self,instruction,obs,**kwargs):
                assert instruction=='public task'
                assert set(obs)=={'screenshot'}
                return '', ['DONE'], {'suz_status':'visually_accepted'}
            def close(self):pass
        class FakeEnv:
            evaluations=0
            def reset(self,task_config):return {'screenshot':b'png','secret_grader':'hidden'}
            def step(self,action,pause=0):
                assert action=='DONE'
                return {'screenshot':b'png','secret_grader':'hidden'},0,True,{}
            def evaluate(self):self.evaluations+=1;return 0.75
        with tempfile.TemporaryDirectory() as folder:
            env=FakeEnv();result=run_task(FakeAgent(),env,{'id':'T','instruction':'public task','evaluator':'hidden'},folder)
            self.assertEqual(env.evaluations,1)
            self.assertEqual(result['official_score'],0.75)

    def test_baseline_has_no_suz_roles_or_guidance(self):
        image=Image.new('RGB',(560,560),'white');buf=io.BytesIO();image.save(buf,format='PNG')
        received=[]
        def sender(payload):
            received.append(payload)
            return response('## Action\nFinish\n```python\ncomputer.terminate(status="success")\n```')
        with tempfile.TemporaryDirectory() as folder:
            cfg=configuration();cfg['mode']='opencua_baseline'
            meter=MeteredClient(cfg,folder,sender=sender);agent=SUZAgent(cfg,folder,client=meter)
            try:
                _,actions,info=agent.predict('inspect desktop',{'screenshot':buf.getvalue()})
                self.assertEqual(actions,['DONE']);self.assertEqual(info['official_success'],None)
                self.assertEqual([r['role'] for r in meter.calls.values()],['solver'])
                self.assertNotIn('SUZ controller guidance',json.dumps(received))
            finally:agent.close()

    def test_official_predict_real_bridge_and_critic_reject_then_accept(self):
        """Actual pinned agent + Node controller; scripted responses, no network/desktop."""
        image=Image.new('RGB',(560,560),'white'); buf=io.BytesIO();image.save(buf,format='PNG')
        png=buf.getvalue();calls=[];solver_count=0;review_count=0
        instruction='Save report.txt'
        def sender(payload):
            nonlocal solver_count,review_count
            system=payload['messages'][0]['content'];calls.append(payload)
            if 'stage=plan' in system: # Critic prompt contains both stage descriptions.
                text=payload['messages'][-1]['content'][0]['text'];ctx=json.loads(text)
                if ctx['stage']=='plan':result={'obligations':[{'id':'G1','quote':'report.txt','predicate':'saved file'}]}
                else:
                    review_count+=1
                    result={'decision':'revise' if review_count==1 else 'accept','assessments':[
                        {'id':o['id'],'status':'unknown' if review_count==1 else 'met','frame_ids':[ctx['frame_id']],
                         'reason':'inspect saved filename','basis':'insufficient' if review_count==1 else 'visible_result',
                         'next_step':'reopen saved document'} for o in ctx['obligations']]}
                return response(json.dumps(result))
            if "semantic direction planner" in system:
                return response(json.dumps({'task_model':{'problem':instruction,'environment':'editor','unknowns':[]},
                  'new_routes':[{'id':'N1','hypothesis':'save via menu','mechanism':'open save dialog','target':'editor',
                    'steps':['open dialog','save and inspect'],'progress_signal':'filename visible','abandon_when':'dialog absent','evidence_ids':[]}],
                  'evaluations':[{'route_id':'N1','suitability':1,'disposition':'retain','reason':'available','evidence_ids':[]}],
                  'reason':'save goal','evidence_ids':[]}))
            if 'BEFORE and AFTER' in system:
                ctx=json.loads(payload['messages'][-1]['content'][0]['text'])
                return response(json.dumps({'verdict':'uncertain','reason':'requires inspection','evidence_ids':list(ctx['evidence'])[-1:],'memories':[]}))
            solver_count+=1
            if solver_count in [1,3]:action='pyautogui.click(x=280, y=280)'
            else:action='computer.terminate(status="success")'
            return response('## Observation\nEditor visible\n## Thought\nCheck save\n## Action\nInspect file\n```python\n'+action+'\n```')
        with tempfile.TemporaryDirectory() as folder:
            cfg=configuration();meter=MeteredClient(cfg,folder,sender=sender)
            # Block all urllib network paths so accidental transport fallback fails.
            with patch('urllib.request.urlopen',side_effect=AssertionError('network forbidden')):
                agent=SUZAgent(cfg,folder,client=meter)
                try:
                    outputs=[]
                    for _ in range(4):
                        result=agent.predict(instruction,{'screenshot':png,'reward':1,'accessibility_tree':'SECRET_GRADER'})
                        outputs.append(result[1]);agent.record_feedback('unknown','step returned screenshot')
                    self.assertEqual(outputs[0],['pyautogui.click(280, 280)'])
                    self.assertEqual(outputs[1],['WAIT'])
                    self.assertEqual(outputs[3],['DONE'])
                    self.assertEqual(len(agent.actions),3) # rejected completion removed from native history
                    self.assertEqual(agent.bridge.call('snapshot')['review']['official_success'],None)
                    self.assertTrue(all('SECRET_GRADER' not in json.dumps(p) for p in calls))
                    self.assertEqual({r['role'] for r in meter.calls.values()},{'critic','planner','solver','monitor'})
                    self.assertTrue((Path(folder)/'frames/F3.png').exists())
                finally:agent.close()

    def test_solver_transport_stop_bypasses_upstream_retry_loop(self):
        from python.upstream import load_official
        class StopAgent(load_official().OpenCUAAgent):
            n=0
            def call_llm(self,*args):self.n+=1;raise RunStop('budget')
        a=StopAgent(model='opencua-7b',history_type='action_history',max_steps=10)
        with self.assertRaises(RunStop):a.predict('x',{'screenshot':b'image'})
        self.assertEqual(a.n,1)


if __name__=='__main__':unittest.main()
