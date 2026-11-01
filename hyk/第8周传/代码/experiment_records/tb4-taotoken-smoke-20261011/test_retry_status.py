import unittest
from launch_retry1 import summarize

class StatusTests(unittest.TestCase):
    def test_failure_cannot_become_success_when_grading_finishes(self):
        result={'verifier_result':{'rewards':{'reward':0}},'exception_info':None}
        self.assertEqual(summarize(result,{'exit_code':1,'phase':'benchmark'}),'failed_agent_graded')
        self.assertEqual(summarize(result,{'exit_code':65,'phase':'live_gate'}),'failed_live_gate')
        self.assertEqual(summarize(result,{'exit_code':0,'phase':'benchmark'}),'finished_graded')
        self.assertEqual(summarize(result,{}),'failed_agent_graded')
    def test_missing_grade_and_exception(self):
        self.assertEqual(summarize({},{}),'failed_missing_result')
        self.assertEqual(summarize({'exception_info':{'type':'failure'}},{}),'failed_engineering')
        self.assertEqual(summarize({'exception_info':None},{'exit_code':0}),'failed_missing_grade')

if __name__=='__main__': unittest.main()
