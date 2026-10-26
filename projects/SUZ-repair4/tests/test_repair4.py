import io,json,tempfile,unittest
from unittest.mock import patch
from PIL import Image
from python.compat import adapt_response,install_absolute_projector
from python.upstream import load_official
from python.streaming import read_completion
from python.observation import fresh_observation
from python.runtime import MeteredClient,TransientTransport,RunStop
from test_runtime import configuration,response


class Repair4Tests(unittest.TestCase):
    def parse(self,code):
        module=load_official();install_absolute_projector(module)
        value=adapt_response('```python\n'+code+'```',(1920,1080))
        return module.parse_response_to_cot_and_action(value,(1920,1080),'absolute')[1]

    def test_exact_failed_waits_preserve_preceding_actions(self):
        self.assertEqual(self.parse('{"name":"computer.wait","parameters":{}}'),['WAIT'])
        actions=self.parse('pyautogui.press("escape")\npyautogui.press("f5")\n{"name":"computer.wait","parameters":{}}')
        self.assertIn("pyautogui.press('escape')",actions[0]);self.assertIn("pyautogui.press('f5')",actions[0])
        self.assertIn('pyautogui.sleep(',actions[0])
        self.assertEqual(self.parse('pyautogui.sleep(40)'),['pyautogui.sleep(30)\npyautogui.sleep(10)'])
        for code in ['{"name":"os.system","parameters":{}}','pyautogui.sleep(40)\npyautogui.sleep(40)','pyautogui.sleep(61)']:
            with self.assertRaises(ValueError):self.parse(code)

    def stream(self,chunks):
        return io.BytesIO((''.join('data: '+json.dumps(c,ensure_ascii=False)+'\n\n' for c in chunks)+'data: [DONE]\n\n').encode())

    def test_stream_separates_reasoning_and_requires_complete_usage(self):
        chunks=[{'choices':[{'index':0,'delta':{'reasoning_content':'推理'}}]},
          {'choices':[{'index':0,'delta':{'content':'安全'}}]},
          {'choices':[{'index':0,'delta':{'content':'动作'},'finish_reason':'stop'}]},
          {'choices':[],'usage':{'prompt_tokens':2,'completion_tokens':3}}]
        out=read_completion(self.stream(chunks),float('inf'))
        self.assertEqual(out['choices'][0]['message'],{'content':'安全动作','reasoning_content':'推理'})
        with self.assertRaises(ValueError):read_completion(self.stream(chunks[:-1]),float('inf'))
        with self.assertRaises(ValueError):read_completion(io.BytesIO(b'data: {"choices":[]}\n\n'),float('inf'))
        with self.assertRaises(ValueError):read_completion(self.stream(chunks),0)

    def test_truncation_then_transport_can_complete_within_three_requests(self):
        with tempfile.TemporaryDirectory() as folder:
            cfg=configuration();cfg.update(bounded_response_recovery=True,initial_output_tokens=100,truncation_recovery_tokens=200,max_output_tokens=200)
            calls=[]
            def sender(payload):
                calls.append(payload['max_tokens'])
                if len(calls)==1:return response(choices=[{'finish_reason':'length'}])
                if len(calls)==2:raise TransientTransport('disconnect')
                return response('final')
            client=MeteredClient(cfg,folder,sender=sender)
            self.assertEqual(client.complete('solver',{}),'final');self.assertEqual(calls,[100,200,200])
            self.assertEqual(client.calls[2]['status'],'reserved')

    def test_missing_screenshot_reacquires_without_action(self):
        buf=io.BytesIO();Image.new('RGB',(10,10)).save(buf,format='PNG');png=buf.getvalue()
        class Controller:
            calls=0
            def get_screenshot(self):
                self.calls+=1;return b'broken' if self.calls==1 else png
        class Env:
            controller=Controller()
            def step(self,*a,**k):raise AssertionError('action replay forbidden')
        env=Env()
        with patch('python.observation.time.sleep'):
            self.assertEqual(fresh_observation(env,{'screenshot':None})['screenshot'],png)
            self.assertEqual(env.controller.calls,2)
            with patch.object(env.controller,'get_screenshot',return_value=None):
                with self.assertRaisesRegex(RuntimeError,'bounded'):fresh_observation(env,{'screenshot':None})

if __name__=='__main__':unittest.main()
