import unittest
from outcomes import classify

class Outcomes(unittest.TestCase):
    def result(self):
        return {'process_exit_code':0, 'exception_info':None, 'verifier_result':{'rewards':{'score':0}}}
    def test_hai_deadline(self):
        events=[{'event':'model_error','error_type':'ModelError'},
                {'event':'method_end','result':{'stop_reason':'wall_budget'}}]
        self.assertTrue(classify(self.result(),events)['infrastructure_ok'])
    def test_graph_deadline(self):
        self.assertTrue(classify(self.result(),[{'event':'method_end','stop_reason':'wall_budget_exhausted'}])['infrastructure_ok'])
    def test_real_model_error(self):
        self.assertFalse(classify(self.result(),[{'event':'model_error'}, {'event':'method_end','result':{'stop_reason':'api_error'}}])['infrastructure_ok'])
    def test_adapter_not_hidden(self):
        self.assertFalse(classify(self.result(),[{'event':'adapter_error'},{'event':'method_end','stop_reason':'wall_budget_exhausted'}])['infrastructure_ok'])
    def test_earlier_error_not_hidden(self):
        self.assertFalse(classify(self.result(),[{'event':'model_error'},{'event':'tool_start'},{'event':'method_end','stop_reason':'wall_budget_exhausted'}])['infrastructure_ok'])
    def test_zero_reward_is_normal(self):
        self.assertTrue(classify(self.result(),[{'event':'method_end','stop_reason':'submit'}])['infrastructure_ok'])

if __name__=='__main__': unittest.main()
