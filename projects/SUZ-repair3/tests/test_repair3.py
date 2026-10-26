import json
import tempfile
import unittest
from pathlib import Path
from python.compat import adapt_response
from python.actions import validate_actions
from python.runtime import MeteredClient, RunStop, TransientTransport
from test_runtime import configuration, response


class Repair3Tests(unittest.TestCase):
    def test_single_block_missing_heading_and_inline_backticks(self):
        value=adapt_response('Use ```code inline in explanation\n```python\npyautogui.click(300, 400)\n```',(1920,1080))
        self.assertIn('## Action:',value)
        self.assertIn('pyautogui.click(300, 400)',value)
        from python.upstream import load_official
        from python.compat import install_absolute_projector
        official=load_official();install_absolute_projector(official)
        _,actions,_=official.parse_response_to_cot_and_action(value,(1920,1080),'absolute')
        self.assertEqual(actions,['pyautogui.click(300, 400)'])
        with self.assertRaisesRegex(ValueError,'ambiguous'):
            adapt_response('```python\npyautogui.click(1,2)\n```\n```python\npyautogui.click(3,4)\n```',(1920,1080))

    def test_control_status_not_explanatory_text_controls_result(self):
        for status,expected in [('failure','fail'),('success','success')]:
            value=adapt_response('```python\ncomputer.terminate(status="'+status+'", answer="""failure code 10.5abc\ncontinued""")\n```',(1920,1080))
            self.assertIn("computer.terminate(status='"+expected+"')",value)
            self.assertNotIn('answer=',value)

    def test_wait_retains_duration_with_bound(self):
        for duration in (15,20,30):validate_actions(['time.sleep('+str(duration)+')'])
        with self.assertRaises(ValueError):validate_actions(['time.sleep(31)'])

    def client(self,folder,sender):
        cfg=configuration();cfg.update(bounded_response_recovery=True,max_requests=10,
            initial_output_tokens=100,truncation_recovery_tokens=200,max_output_tokens=200)
        return MeteredClient(cfg,folder,sender=sender)

    def test_disconnect_retries_once_and_retains_unknown_charge(self):
        with tempfile.TemporaryDirectory() as folder:
            count=0
            def send(_):
                nonlocal count
                count+=1
                if count==1:raise TransientTransport('disconnect')
                return response()
            client=self.client(folder,send)
            self.assertEqual(client.complete('solver',{}),'ok')
            self.assertEqual(count,2)
            self.assertEqual(client.calls[1]['status'],'reserved')
            self.assertEqual(client.calls[2]['status'],'settled')
            self.assertGreater(client.spent,client.calls[1]['charge_cny'])

    def test_reasoning_only_never_executed_both_requests_charged(self):
        with tempfile.TemporaryDirectory() as folder:
            outputs=iter([response(choices=[{'finish_reason':'stop','message':{'reasoning_content':'pyautogui.click(1,2)'}}]),response('safe final')])
            client=self.client(folder,lambda _:next(outputs))
            self.assertEqual(client.complete('solver',{}),'safe final')
            self.assertEqual([r['status'] for r in client.calls.values()],['settled','settled'])

    def test_mixed_failure_never_exceeds_two_requests(self):
        with tempfile.TemporaryDirectory() as folder:
            count=0
            def send(_):
                nonlocal count
                count+=1
                if count==1:return response(choices=[{'finish_reason':'length'}])
                raise TransientTransport('disconnect')
            client=self.client(folder,send)
            with self.assertRaises(RunStop):client.complete('critic',{})
            self.assertEqual(count,2)

    def test_permanent_failure_not_retried(self):
        with tempfile.TemporaryDirectory() as folder:
            def send(_):raise RunStop('HTTP 401')
            client=self.client(folder,send)
            with self.assertRaises(RunStop):client.complete('solver',{})
            self.assertEqual(len(client.calls),1)

