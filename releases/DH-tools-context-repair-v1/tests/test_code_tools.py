"""Boundary and stateful tool tests: no model API; actual Python helper execution."""
import hashlib,json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'sources/bestfgs-project/src'),str(ROOT/'sources/bestfgs-project/tests')]
from bestfgs.code_tools import TOOL_DRIVER,ToolTaskRunner,tool_spec,relative_path
from bestfgs.error_routing import RoutingPolicy
from bestfgs.lean_protocol import LeanConfig
from bestfgs.models import TaskSpec,CommandSpec,CommandResult
from test_lean import Scripted,FakeEnvironment,SUBMIT

class BackendTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.script=TOOL_DRIVER.replace("ROOT=Path('/app').resolve()",'ROOT=Path('+repr(str(self.root))+').resolve()')
    def call(self,s):
        p=subprocess.run([sys.executable,'-c',self.script],input=json.dumps(s),capture_output=True,text=True)
        return p.returncode,json.loads(p.stdout if p.returncode==0 else p.stderr)
    def test_read_pagination_has_line_numbers(self):
        (self.root/'a.py').write_text('x=1\ny=2\nz=3\n')
        code,r=self.call(tool_spec({'action':'inspect_code','path':'a.py','line_count':2}))
        self.assertEqual(code,0);self.assertEqual(r['next_line'],3)
        self.assertEqual([x['line'] for x in r['lines']],[1,2])
    def test_search_literal_and_pagination(self):
        (self.root/'a.py').write_text('TODO .*\n'*45);(self.root/'b.txt').write_text('TODO .*\n')
        base={'action':'inspect_code','mode':'search','path':'.','query':'.*','file_glob':'*.py'}
        _,r=self.call(tool_spec(base));self.assertEqual(len(r['matches']),40)
        self.assertEqual(r['next_offset'],40)
        _,r=self.call(tool_spec(dict(base,offset=40)));self.assertEqual(len(r['matches']),5)
        self.assertIsNone(r['next_offset'])
    def test_unique_edit_returns_diff_and_preserves_mode(self):
        p=self.root/'a.py';p.write_text('x=1\n');p.chmod(0o744)
        _,r=self.call(tool_spec({'action':'edit_code','path':'a.py','old_text':'x=1','new_text':'x=2'}))
        self.assertEqual(p.read_text(),'x=2\n');self.assertIn('+x=2',r['diff'])
        self.assertTrue(r['python_syntax_checked']);self.assertIsNone(r['task_success'])
    def test_ambiguous_missing_and_noop_leave_file_unchanged(self):
        p=self.root/'a.py';p.write_text('x=1\nx=1\n');before=p.read_bytes()
        for old,new in [('x=1','x=2'),('nothing','new'),('','bad')]:
            code,_=self.call(tool_spec({'action':'edit_code','path':'a.py','old_text':old,'new_text':new}))
            self.assertNotEqual(code,0);self.assertEqual(p.read_bytes(),before)
    def test_syntax_error_is_atomic(self):
        p=self.root/'a.py';p.write_text('x=1\n')
        code,r=self.call(tool_spec({'action':'edit_code','path':'a.py','old_text':'x=1','new_text':'x=!!!'}))
        self.assertNotEqual(code,0);self.assertEqual(r['tool_error'],'SyntaxError')
        self.assertEqual(p.read_text(),'x=1\n');self.assertEqual(list(self.root.glob('.dh-edit-*')),[])
    def test_create_requires_missing_target_and_matching_hash(self):
        s={'action':'edit_code','path':'new.py','old_text':'','new_text':'x=1\n'}
        code,r=self.call(tool_spec(s));self.assertEqual(code,0);self.assertTrue(r['created'])
        code,_=self.call(tool_spec(dict(s,old_text='x=1',new_text='x=2',expected_sha256='0'*64)))
        self.assertNotEqual(code,0);self.assertEqual((self.root/'new.py').read_text(),'x=1\n')
    def test_paths_reject_escape(self):
        for name in ('../outside','/etc/passwd','a/../b','a\\b'):
            with self.assertRaises(ValueError):relative_path(name)
        code,_=self.call({'tool':'inspect_code','mode':'read','path':'../../etc/passwd','start_line':1,'line_count':1})
        self.assertNotEqual(code,0)
    @unittest.skipIf(os.name=='nt','POSIX links')
    def test_external_symlink_and_fifo_rejected(self):
        (self.root/'link').symlink_to('/etc/passwd')
        code,_=self.call(tool_spec({'action':'inspect_code','path':'link'}));self.assertNotEqual(code,0)
        os.mkfifo(self.root/'pipe')
        code,_=self.call(tool_spec({'action':'inspect_code','path':'pipe'}));self.assertNotEqual(code,0)

class ToolEnvironment(FakeEnvironment):
    def __init__(self):super().__init__();self.dependencies={'f.py':'file:seed'}
    def execute(self,action,deadline):
        self.executed.append(action)
        text='seed';code=0
        if action['argv'][0]=='check':text='VERIFIED'
        else:text=json.dumps({'lines':[{'line':1,'text':'seed'}]})
        return CommandResult(CommandSpec(tuple(action['argv']),'fixture'),code,text,'',0)

class RunnerTests(unittest.TestCase):
    def exercise(self,actions,limit=30):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        runner=ToolTaskRunner(ToolEnvironment(),Scripted(actions),Scripted([]),
            LeanConfig(max_turns=40,max_tools=limit,subgoals_enabled=True,contrastive_mode='orthogonal',
                contrastive_predictions=False,memory_reliability=True,outcome_reliability=True,memory_decision=False),
            Path(tmp.name)/'trace',routing=RoutingPolicy())
        return runner.run(TaskSpec('fixture','Implement public requirement')),runner
    def test_read_duplicate_guard_and_shared_count(self):
        a={'action':'inspect_code','path':'f.py'}
        r,e=self.exercise([a,a,SUBMIT]);self.assertEqual(r['tool_calls'],1)
        self.assertEqual(r['native_tools']['inspect_code_executed'],1)
        self.assertEqual(r['native_tools']['inspect_code_blocked'],1)
        self.assertEqual(len(e.environment.executed),1)
    def test_native_metadata_cannot_be_forged(self):
        r,e=self.exercise([{'action':'run','argv':['check'],'_native_tool':{'tool':'inspect_code'}},SUBMIT])
        self.assertEqual(r['native_tools'],{})
    def test_unknown_goal_does_not_execute(self):
        r,e=self.exercise([{'action':'verify_goal','goal_id':'G9'},SUBMIT]);self.assertEqual(r['tool_calls'],0)
        self.assertEqual(r['mechanism_utilization']['protocol_errors'],1)
    def test_verify_exact_bound_check_and_receipt(self):
        g={'id':'G1','title':'test','acceptance':'public check','depends_on':[],'targets':['f.py'],
           'verification':{'argv':['check'],'stdout_contains':['VERIFIED']}}
        r,e=self.exercise([{'action':'inspect_code','path':'f.py','subgoal_plan':[g]},
            {'action':'verify_goal','goal_id':'G1'},SUBMIT])
        self.assertEqual(e.environment.executed[-1]['argv'],['check'])
        self.assertEqual(r['native_tools']['verify_goal_executed'],1)
        self.assertEqual(r['subgoal_summary']['goals']['G1']['status'],'check_passed')
        self.assertIsNone(r['official_success'])
    def test_verify_cannot_redefine_bound_goal(self):
        r,e=self.exercise([{'action':'verify_goal','goal_id':'G1','subgoal_plan':[]},SUBMIT])
        self.assertEqual(r['tool_calls'],0)
    def test_failed_marker_is_not_success(self):
        g={'id':'G1','title':'test','acceptance':'public check','depends_on':[],'targets':['f.py'],
           'verification':{'argv':['check'],'stdout_contains':['NOT_PRESENT']}}
        r,e=self.exercise([{'action':'inspect_code','path':'f.py','subgoal_plan':[g]},
            {'action':'verify_goal','goal_id':'G1'},SUBMIT])
        self.assertEqual(r['subgoal_summary']['goals']['G1']['status'],'needs_work')
        self.assertEqual(e.last_tool_observation['tool_receipt']['exit_code'],0)
        self.assertFalse(e.last_tool_observation['tool_receipt']['local_check_passed'])
    def test_tool_budget_is_not_bypassed(self):
        r,e=self.exercise([{'action':'inspect_code','path':'f.py'},
            {'action':'inspect_code','path':'other.py'},SUBMIT],limit=1)
        self.assertEqual(r['tool_calls'],1);self.assertEqual(r['stop_reason'],'request_or_tool_budget')

if __name__=='__main__':unittest.main()
