import sys
import unittest
from pathlib import Path
from copy import deepcopy
root=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(root/'recuris-dsh/vendor'),str(root/'taco-dsh/vendor')]
from recuris import memory, working
from taco_native.compression import CompressionRule, DynamicCompressionFilter, FeedbackCollector
from taco_native.output_filter import FilterContext, FilterState

class RecurisTests(unittest.TestCase):
    def setUp(self):
        self.m=memory.load_memory(root/'recuris-dsh/vendor/terminal_seed.json')
        self.w=working.initialize({'goals':[{'id':'g','description':'build artifact','verification':{'command':'python check.py','contains':['PASS']}}]},8)
        self.p={'updates':[{'goal_id':'g','status':'done','evidence_ids':['old'],'blocker':''}],'new_goals':[],'revised_verifications':[]}
        self.r={'old':{'kind':'verification','goal_id':'g','revision':3,'verification_digest':working.verifier_digest(self.w[0]['verification']),
            'completed':True,'exit_code':0,'synthetic':False,'output':'PASS'}}
    def test_current_receipt(self):
        w,d=working.apply_proposal(self.w,self.p,self.r,3,self.m)
        self.assertTrue(d[0]['accepted']);self.assertEqual(w[0]['status'],'done')
    def test_old_id_still_valid_when_not_stale(self):
        self.r.update({f'E{i}':{'output':'irrelevant'} for i in range(200)})
        self.assertTrue(working.apply_proposal(self.w,self.p,self.r,3,self.m)[1][0]['accepted'])
    def test_stale_or_fabricated_or_failed_receipt(self):
        for field,value in [('revision',2),('exit_code',1),('completed',False),('synthetic',True),('goal_id','other')]:
            r=deepcopy(self.r);r['old'][field]=value
            self.assertFalse(working.apply_proposal(self.w,self.p,r,3,self.m)[1][0]['accepted'])
        self.assertFalse(working.apply_proposal(self.w,self.p,{},3,self.m)[1][0]['accepted'])
    def test_changed_verification_invalidates(self):
        self.p['revised_verifications']=[{'goal_id':'g','verification':{'command':'python -u check.py','contains':['PASS']}}]
        self.assertFalse(working.apply_proposal(self.w,self.p,self.r,3,self.m)[1][0]['accepted'])
    def test_completion_reopens_after_mutation(self):
        w,_=working.apply_proposal(self.w,self.p,self.r,3,self.m)
        self.assertEqual(working.invalidate_completions(w)[0]['status'],'pending')
    def test_state_conditioned_retrieval(self):
        self.m['rho']={'trigger':'on_unresolved_change','retrieval':'lexical','max_skills':2}
        self.m['E']=[{'id':'build','description':'build artifact','content':'Run build','tags':['build']},{'id':'web','description':'browse web','content':'Web','tags':['web']}]
        self.assertEqual(memory.invoke(self.m,self.w,1,None)[0]['id'],'build')
        self.assertEqual(memory.invoke(self.m,self.w,2,memory.unresolved_signature(self.w)),[])

class TacoTests(unittest.TestCase):
    def test_error_is_not_compression_complaint(self):
        f=FeedbackCollector();f.record_compression(1,'make','failed','failed',[])
        self.assertIsNone(f.detect_complaint(2,'tool failed',analysis='tool failed'))
    def test_dynamic_filter_preserves_errors(self):
        r=CompressionRule(rule_id='r',trigger_regex='make',strip_patterns=['.*'])
        d=DynamicCompressionFilter(r)
        self.assertTrue(d.should_skip(FilterContext('make',True,FilterState.IDLE,None,9000)))
    def test_explicit_and_heuristic_feedback(self):
        for kw in [{'compression_feedback':'need_full_output'},{'analysis':'need full output'},{'commands':['make']}]:
            f=FeedbackCollector();f.record_compression(1,'make','raw','filtered',['r'])
            self.assertIsNotNone(f.detect_complaint(2,'feedback',**kw))
    def test_uncovered_threshold(self):
        f=FeedbackCollector()
        self.assertIsNone(f.detect_uncovered(1,'x','x'*3000,[],threshold=3000))
        self.assertIsNotNone(f.detect_uncovered(1,'x','x'*3001,[],threshold=3000))

if __name__=='__main__':unittest.main(verbosity=2)
