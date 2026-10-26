import unittest
from types import SimpleNamespace
from appworld_guard import AppWorldGuard,answer_contract,collect_pages

DOCS={'phone':{'send_text_message':{'method':'POST'},'search_text_messages':{'method':'GET','parameters':[{'name':'page_index'}]},'login':{'method':'POST'}},
      'supervisor':{'complete_task':{'method':'POST'}},'venmo':{'export_transactions':{'method':'GET'}}}

class GuardTests(unittest.TestCase):
    def setUp(self):
        self.g=AppWorldGuard('Send a message to my partner.',DOCS);self.calls=[]
    def request(self,**kwargs):
        self.calls.append(kwargs);return SimpleNamespace(status_code=200)
    def test_readonly_blocks_write_and_get_export_before_execution(self):
        self.g.read_only=True
        for app,api in [('phone','send_text_message'),('venmo','export_transactions')]:
            with self.assertRaisesRegex(RuntimeError,'READ_ONLY'):self.g.invoke(self.request,app,api)
        self.assertFalse(self.calls)
    def test_auth_and_reads_allowed(self):
        self.g.read_only=True
        self.g.invoke(self.request,'phone','login')
        self.g.invoke(self.request,'phone','search_text_messages')
        self.assertEqual(len(self.calls),2);self.assertEqual(self.g.revision,0)
        self.assertEqual(self.g.events[-1]['kind'],'partial_page_warning')
    def test_submission_blocks_probe_even_after_local_delete_plan(self):
        self.g.invoke(self.request,'phone','send_text_message',message='requested')
        self.g.invoke(self.request,'supervisor','complete_task',answer='unrequested prose')
        self.assertIsNone(self.calls[-1]['answer'])
        with self.assertRaises(RuntimeError):self.g.invoke(self.request,'phone','send_text_message',message='probe')
        self.g.invoke(self.request,'supervisor','complete_task')
        self.assertEqual(len(self.calls),2)
    def test_failed_submission_does_not_seal(self):
        self.g.invoke(lambda **kw:SimpleNamespace(status_code=400),'supervisor','complete_task')
        self.assertFalse(self.g.submitted)
    def test_answer_contract_preserves_information_requests_and_unknown(self):
        self.assertEqual(answer_contract('How many songs are in my playlist?'),'answer')
        self.assertEqual(answer_contract('Send the message, then tell me how many were sent.'),'answer')
        self.assertEqual(answer_contract('Import all markdown notes.'),'state_only')
        self.assertEqual(answer_contract('Please help with my account'),'unspecified')
    def test_requested_answer_preserved(self):
        g=AppWorldGuard('How many contacts do I have?',DOCS)
        g.invoke(self.request,'supervisor','complete_task',answer=12)
        self.assertEqual(self.calls[-1]['answer'],12)
    def test_pages_exhaustion_even_when_short_page(self):
        pages=[[1,2],[3],[]];seen=[]
        result=collect_pages(lambda **kw:(seen.append(kw['page_index']) or pages[kw['page_index']]))
        self.assertEqual(result,[1,2,3]);self.assertEqual(seen,[0,1,2])
    def test_repeated_page_and_nonlist_fail_closed(self):
        with self.assertRaises(RuntimeError):collect_pages(lambda **kw:[1])
        with self.assertRaises(TypeError):collect_pages(lambda **kw:{'results':[1]})
    def test_max_pages_does_not_silently_truncate(self):
        with self.assertRaises(RuntimeError):collect_pages(lambda **kw:[kw['page_index']],max_pages=2)

if __name__=='__main__':unittest.main()
