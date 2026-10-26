import tempfile
import unittest
from python.run_osworld import run_task


class Agent:
    max_steps=1
    class client:
        spent=0
        calls=[]
    def __init__(self,signal,status):self.signal,self.status=signal,status
    def predict(self,*args,**kwargs):return '',[self.signal],{'suz_status':self.status}
    def close(self):pass


class Environment:
    def __init__(self):self.actions=[]
    def reset(self,**kwargs):return {'screenshot':b'x'}
    def step(self,action,**kwargs):self.actions.append(action);return {'screenshot':b'x'},0,True,{}
    def evaluate(self):return int(self.actions==['FAIL'])


class TerminalSignalTests(unittest.TestCase):
    def test_only_intentional_fail_reaches_official_infeasible_grader(self):
        for status,score in [('solver_declared_fail',1),('all-role budget cannot reserve next request',0),
                             ('model transport failed',0),('Solver stopped without completion',0)]:
            with self.subTest(status=status), tempfile.TemporaryDirectory() as folder:
                env=Environment()
                result=run_task(Agent('FAIL',status),env,{'id':'probe','instruction':'probe'},folder)
                self.assertEqual(result['official_score'],score)
