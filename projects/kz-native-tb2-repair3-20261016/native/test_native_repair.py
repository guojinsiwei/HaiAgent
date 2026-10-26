import json
import sys
import tempfile
import unittest
from pathlib import Path
import solve
from native_repair import RepairLedger, RepairRunner
from bestfgs.lean_protocol import parse_action


class Scripted:
    def __init__(self, values):
        self.values = iter(values)
        self.prompts = []
    def complete_json(self, **kwargs):
        self.prompts.append(kwargs)
        return next(self.values)
    def usage_summary(self):
        return {'api_requests': 0}


def goal(target='check.py'):
    return dict(id='G1', title='public check', acceptance='check actual file contents',
                depends_on=[], targets=[target],
                verification=dict(argv=['python3', 'check.py'], cwd='.', stdout_contains=['CHECK_OK']))


class Repairs(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = self.root / 'workspace'
        self.workspace.mkdir()
        self.ledger = RepairLedger(self.workspace, lambda *a, **kw: None)

    def test_long_summary_retained_without_truncation(self):
        s = 'delivered artifact; ' * 500
        self.assertEqual(parse_action(dict(action='submit', summary=s))['summary'], s)
        for value in ['', None, {'text': 'x'}, '\x00']:
            with self.assertRaises(ValueError): parse_action(dict(action='submit', summary=value))

    def test_absolute_targets_inside_workspace(self):
        g = goal(str(self.workspace / 'check.py'))
        self.ledger.begin(dict(action='run', argv=['ls'], subgoal_plan=[g], subgoal_id='G1'))
        self.assertEqual(self.ledger.items['G1']['definition']['targets'], ['check.py'])
        with self.assertRaises(ValueError):
            self.ledger.begin(dict(action='run', argv=['ls'], subgoal_plan=[goal(str(self.root / 'outside'))]))

    def test_rejected_plan_remains_visible_until_corrected(self):
        g = goal(); del g['verification']['stdout_contains']
        with self.assertRaises(ValueError):
            self.ledger.begin(dict(action='run', argv=['ls'], subgoal_plan=[g], subgoal_id='G1'))
        for _ in range(4):
            with self.assertRaises(ValueError): self.ledger.begin(dict(action='run', argv=['ls'], subgoal_id='G1'))
        panel = self.ledger.view()
        self.assertIn('output assertions', panel['plan_error'])
        self.assertEqual(panel['unregistered_plan'][0]['id'], 'G1')
        self.assertFalse(self.ledger.items)
        self.ledger.begin(dict(action='run', argv=['ls'], subgoal_plan=[goal()], subgoal_id='G1'))
        self.assertNotIn('unregistered_plan', self.ledger.view())

    def test_literal_shell_wrapper_matches_check(self):
        self.ledger.begin(dict(action='run', argv=['ls'], subgoal_plan=[goal()], subgoal_id='G1'))
        cmd=dict(action='run', argv=['bash', '-lc', 'cd '+shlex_quote(str(self.workspace))+' && python3 check.py'], subgoal_id='G1', subgoal_phase='verify')
        self.assertEqual(self.ledger.begin(cmd)['phase'], 'verify')
        self.assertEqual(cmd['argv'][0], 'bash')
        for tail in [' && false', '; true', ' > other.txt', ' | cat']:
            other=dict(cmd, argv=['bash','-lc',cmd['argv'][2]+tail])
            self.assertEqual(self.ledger.begin(other)['phase'], 'work')

    def test_wrong_check_never_commits_done(self):
        self.ledger.begin(dict(action='run', argv=['ls'], subgoal_plan=[goal()], subgoal_id='G1'))
        self.assertEqual(self.ledger.begin(dict(action='run', argv=['echo','CHECK_OK'], subgoal_id='G1', subgoal_phase='verify'))['phase'], 'work')
        self.assertEqual(self.ledger.items['G1']['status'], 'pending')

    def test_cross_task_ledger_isolation(self):
        self.ledger.begin(dict(action='run', argv=['ls'], subgoal_plan=[goal()], subgoal_id='G1'))
        other = RepairLedger(self.workspace, lambda *a, **kw: None)
        self.assertFalse(other.items)

    def test_real_loop_recovers_after_four_bad_actions(self):
        (self.workspace/'check.py').write_text('from pathlib import Path\nassert Path("data.txt").read_text()=="ok"\nprint("CHECK_OK")\n')
        (self.workspace/'data.txt').write_text('ok')
        g=goal(str(self.workspace/'data.txt'))
        actor=Scripted([dict(action='bogus') for _ in range(4)]+[
            dict(action='run',argv=['python3','check.py'],subgoal_plan=[g],subgoal_id='G1',subgoal_phase='verify'),
            dict(action='submit',summary='complete '*500)])
        engine=RepairRunner(solve.InPlace(self.workspace,self.root/'state'),actor,Scripted([]),
            solve.LeanConfig(max_turns=30,max_tools=20,wall_seconds=120,subgoals_enabled=True,outcome_reliability=True,max_consecutive_errors=sys.maxsize),
            self.root/'trace',routing=solve.RoutingPolicy(critic=False))
        result=engine.run(solve.TaskSpec('fixture','Check file contents and deliver.'))
        self.assertTrue(result['submitted'],result)
        self.assertEqual(result['tool_calls'],1)
        self.assertEqual(result['mechanism_utilization']['protocol_errors'],4)
        self.assertEqual(result['subgoal_summary']['goals']['G1']['status'],'check_passed')
        self.assertTrue(any('G1' in p.get('user_prompt','') for p in actor.prompts[5:]))

    def test_critic_does_not_auto_deliver_after_two_reviews(self):
        actor=Scripted([dict(action='submit',summary='candidate') for _ in range(3)])
        review=dict(decision='revise',requirements=['public requirement'],gaps=['needs work'],checks=[dict(argv=['python3','-c','print("CHECK")'],stdout_contains=['CHECK'])])
        verdict=dict(decision='revise',requirements=['public requirement'],gaps=['needs work'],checks=[])
        critic=Scripted([review,verdict]*3)
        engine=RepairRunner(solve.InPlace(self.workspace,self.root/'state'),actor,Scripted([]),
            solve.LeanConfig(max_turns=9,max_tools=10,wall_seconds=120,outcome_reliability=True),self.root/'trace',
            routing=solve.RoutingPolicy(critic=True,critic_limit=sys.maxsize),critic_client=critic)
        result=engine.run(solve.TaskSpec('fixture','Implement public requirement.'))
        self.assertFalse(result['submitted'])
        self.assertEqual(engine.critic_rounds,3)
        self.assertNotEqual(engine.critic_decision,'partial_delivery_review_limit')


def shlex_quote(value):
    import shlex
    return shlex.quote(value)


if __name__=='__main__':unittest.main(verbosity=2)
