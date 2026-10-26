import copy,json,tempfile,unittest
from pathlib import Path
from python.compat import adapt_response,install_absolute_projector
from python.runtime import MeteredClient,RunStop,TransientTransport
from python.upstream import load_official
from test_runtime import configuration,response

class Repair5Tests(unittest.TestCase):
    def parse(self,code):
        m=load_official();install_absolute_projector(m)
        return m.parse_response_to_cot_and_action(adapt_response('```python\n'+code+'\n```',(1920,1080)),(1920,1080),'absolute')[1]

    def test_failed_scholar_batch_preserves_order(self):
        self.assertEqual(self.parse('computer.wait()\npyautogui.click(x=1257, y=630)'),
            ['pyautogui.sleep(1)\npyautogui.click(x=1257, y=630)'])
        self.assertEqual(self.parse('pyautogui.click(20,30)\ncomputer.wait()'),
            ['pyautogui.click(20, 30)\npyautogui.sleep(1)'])
        self.assertEqual(self.parse('computer.wait()'),['WAIT'])
        for code in ['computer.wait(999)','computer.wait(foo=1)',
                     'computer.wait()\nos.system("bad")',
                     'pyautogui.click(20,30)\ncomputer.terminate(status="success")',
                     'computer.wait()\n'+ '\n'.join(['pyautogui.sleep(30)']*3)]:
            with self.assertRaises(ValueError):self.parse(code)

    def config(self):
        cfg=configuration();cfg.update(initial_output_tokens=100,truncation_recovery_tokens=200,
            max_output_tokens=200,bounded_response_recovery=True,output_recovery_reasoning_effort='low')
        return cfg

    def test_empty_truncated_reasoning_gets_bounded_low_effort_recovery(self):
        with tempfile.TemporaryDirectory() as d:
            sent=[]
            def send(p):
                sent.append(copy.deepcopy(p))
                if len(sent)==1:return response(choices=[{'finish_reason':'length','message':{'content':'','reasoning_content':'thinking'}}])
                return response('complete action')
            client=MeteredClient(self.config(),d,sender=send)
            original={'messages':[{'role':'user','content':'Task'}]}
            self.assertEqual(client.complete('solver',original),'complete action')
            self.assertNotIn('reasoning_effort',sent[0]);self.assertEqual(sent[1]['reasoning_effort'],'low')
            self.assertEqual(sent[1]['max_tokens'],200);self.assertNotIn('max_tokens',original)
            self.assertEqual(len(client.calls),2);self.assertTrue(all(x['status']=='settled' for x in client.calls.values()))
            client.complete('solver',original)
            self.assertNotIn('reasoning_effort',sent[2])
            event=json.loads((Path(d)/'recovery-events.jsonl').read_text())
            self.assertEqual(event['reasoning_effort'],'low')

    def test_persistent_truncation_stops_after_two_paid_calls(self):
        with tempfile.TemporaryDirectory() as d:
            client=MeteredClient(self.config(),d,sender=lambda p:response(choices=[{'finish_reason':'length'}]))
            with self.assertRaises(RunStop):client.complete('solver',{})
            self.assertEqual(len(client.calls),2)

    def test_transport_recovery_keeps_default_effort(self):
        with tempfile.TemporaryDirectory() as d:
            sent=[]
            def send(p):
                sent.append(copy.deepcopy(p))
                if len(sent)==1:raise TransientTransport('offline')
                return response('ok')
            client=MeteredClient(self.config(),d,sender=send)
            self.assertEqual(client.complete('solver',{}),'ok')
            self.assertTrue(all('reasoning_effort' not in p for p in sent))
            self.assertEqual(client.calls[1]['status'],'reserved')

if __name__=='__main__':unittest.main()
