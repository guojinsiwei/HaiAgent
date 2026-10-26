"""Email lifecycle/dedup/privacy tests. No real SMTP, model API or credentials."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import experiment_mail as mail

class MailTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);self.root=Path(t.name)
        mail.save(self.root/'protocol.json',{'total_trials':20})
    def status(self,state='generation_complete',scored=20,grade_state='complete_for_available_artifacts'):
        mail.save(self.root/'health.json',{'state':state,'completed':['job'+str(i) for i in range(20)],
            'fatal':None,'pid':99999999,'updated':0})
        mail.save(self.root/'grading-health.json',{'state':grade_state,'scored':scored,'errors':{}})
    def test_no_message_before_launch_or_before_final_grades(self):
        self.assertIsNone(mail.event(self.root))
        self.status(scored=19,grade_state='grading');self.assertIsNone(mail.event(self.root))
    def test_completion_requires_all_scores(self):
        self.status();self.assertEqual(mail.event(self.root)['kind'],'completed')
        self.status(scored=19);self.assertEqual(mail.event(self.root)['reason'],'incomplete_grades')
    def test_abnormal_stop_and_crashed_worker_are_not_success(self):
        self.status(state='needs_attention');self.assertEqual(mail.event(self.root)['kind'],'terminated')
        self.status(state='running')
        with patch.object(mail,'alive',return_value=False):self.assertEqual(mail.event(self.root,now=700)['reason'],'worker_missing')
        with patch.object(mail,'alive',return_value=True):self.assertEqual(mail.event(self.root,now=700)['kind'],'stalled')
    def test_email_has_only_public_summary_and_correct_recipient(self):
        self.status();n=mail.event(self.root);n['reason']='sensitive payload\nnot printable'
        m=mail.message(self.root,n,'5417779@qq.com')
        self.assertEqual(m['To'],'5417779@qq.com');self.assertNotIn('sensitive payload',m.get_content())
        self.assertIn('不调用任何模型',m.get_content())
    def test_accepted_event_not_sent_twice(self):
        self.status();n=mail.event(self.root)
        with patch.object(mail,'connect') as c:
            c.return_value.send_message.return_value={}
            self.assertTrue(mail.deliver(self.root,n,'5417779@qq.com','fixture'))
            self.assertTrue(mail.deliver(self.root,n,'5417779@qq.com','fixture'))
            self.assertEqual(c.return_value.send_message.call_count,1)
        state=(self.root/'notification-state.json').read_text(encoding='utf-8')
        self.assertNotIn('fixture',state)
    def test_ambiguous_send_is_not_claimed_success_or_retried(self):
        self.status();n=mail.event(self.root)
        with patch.object(mail,'connect') as c:
            c.return_value.send_message.side_effect=OSError('fixture transport disconnect')
            self.assertFalse(mail.deliver(self.root,n,'5417779@qq.com','fixture'))
            self.assertFalse(mail.deliver(self.root,n,'5417779@qq.com','fixture'))
            self.assertEqual(c.return_value.send_message.call_count,1)
        self.assertEqual(mail.read(self.root/'notification-state.json')['state'],'delivery_uncertain')
    def test_auth_failure_never_marks_mail_enabled(self):
        with patch.object(mail,'connect',side_effect=RuntimeError('fixture')):
            mail.watch(self.root,'5417779@qq.com','fixture')
        h=mail.read(self.root/'notification-health.json')
        self.assertEqual(h['state'],'configuration_failed');self.assertNotIn('fixture',json.dumps(h))

if __name__=='__main__':unittest.main()
