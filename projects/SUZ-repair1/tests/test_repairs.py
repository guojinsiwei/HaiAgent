import json
import tempfile
import unittest
from python.compat import adapt_response
from python.actions import validate_actions
from python.upstream import load_official
from python.runtime import MeteredClient, RunStop
from python.outcomes import classify
from test_runtime import configuration, response

class Repairs(unittest.TestCase):
    def parsed(self,code):
        text='## Thought:\nInspect\n## Action:\nClick\n```python\n'+code+'\n```'
        fixed=adapt_response(text,(1920,1080))
        _,actions,_=load_official().parse_response_to_cot_and_action(fixed,(1920,1080),'relative')
        return validate_actions(actions)
    def test_real_pixel_failure_and_legacy_and_arithmetic(self):
        self.assertEqual(self.parsed('pyautogui.click(319,76)'),['pyautogui.click(319, 76)'])
        self.assertEqual(self.parsed('pyautogui.click(0.5,0.5)'),['pyautogui.click(960, 540)'])
        self.assertEqual(self.parsed('pyautogui.click(1920/2,1080/2)'),['pyautogui.click(960, 540)'])
        self.assertEqual(self.parsed('pyautogui.click(0,1)'),['pyautogui.click(0, 1)'])
        for code in ['pyautogui.click(3000,100)','pyautogui.click(foo(),20)',
                     'pyautogui.click(2**99999,0)','pyautogui.click(1/0,0)','import os; os.system("a")']:
            with self.assertRaises((ValueError,TypeError,ZeroDivisionError)):self.parsed(code)
    def test_length_recovery_is_bounded_and_charged(self):
        cfg=configuration();cfg.update(max_output_tokens=32768,initial_output_tokens=8192,truncation_recovery_tokens=32768)
        with tempfile.TemporaryDirectory() as folder:
            seen=[]
            def send(p):
                seen.append(p['max_tokens'])
                return response(choices=[{'finish_reason':'length' if len(seen)==1 else 'stop','message':{'content':'ok'}}])
            client=MeteredClient(cfg,folder,sender=send)
            self.assertEqual(client.complete('monitor',{}),'ok')
            self.assertEqual(seen,[8192,32768]);self.assertEqual(len(client.calls),2)
            self.assertTrue(all(x['status']=='settled' for x in client.calls.values()))
        with tempfile.TemporaryDirectory() as folder:
            client=MeteredClient(cfg,folder,sender=lambda p:response(choices=[{'finish_reason':'length'}]))
            with self.assertRaises(RunStop):client.complete('solver',{})
            self.assertEqual(len(client.calls),2)
    def test_classification_counts_caught_stop(self):
        self.assertEqual(classify({'error':None,'agent_status':'unsupported GUI action: argument outside bounds'}),'engineering_failure')
        self.assertEqual(classify({'error':None,'agent_status':'all-role budget cannot reserve next request'}),'resource_limit')

if __name__=='__main__':unittest.main()
