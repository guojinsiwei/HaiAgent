import unittest
from campaign import gate, PILOT

class GateTests(unittest.TestCase):
    def rows(self):return [dict(task=t,state='graded',engineering_clean=True,reward=0) for t in PILOT]
    def test_no_success_holds(self):self.assertFalse(gate(self.rows())['expand'])
    def test_improvement_and_clean_engineering_expands(self):
        rows=self.rows();rows[0]['reward']=1;self.assertTrue(gate(rows)['expand'])
    def test_score_cannot_hide_engineering_fault(self):
        rows=self.rows();rows[0]['reward']=1;rows[2]['engineering_clean']=False
        self.assertFalse(gate(rows)['expand'])
    def test_incomplete_cannot_expand(self):
        rows=self.rows();rows[0]['reward']=1;rows[2]['state']='running'
        self.assertFalse(gate(rows)['expand'])

if __name__=='__main__':unittest.main(verbosity=2)
