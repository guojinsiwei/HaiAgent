"""Behavioral regressions for the failures observed in the 30 real trials."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'sources/bestfgs-project/src'),
               str(ROOT/'sources/bestfgs-project/tests')]
from bestfgs.action_loop import ActionLoopGuard
from bestfgs.contrastive_exploration import command_text
from bestfgs.lean_protocol import LeanConfig
from bestfgs.lean_runtime import LeanTaskRunner
from bestfgs.lean_audit import read_trace
from bestfgs.models import CommandResult, CommandSpec, TaskSpec
from test_lean import FakeEnvironment, Scripted, run_action, SUBMIT


def proposed(action, other=None):
    chosen = dict(id='A', hypothesis='Check a new dependency', action=action,
                  supports='seed', refutes='ERROR')
    rows = [chosen]
    if other is not None:
        rows.append(dict(id='B', hypothesis='Inspect another dependency', action=other,
                         supports='OTHER', refutes='ERROR'))
    return dict(action, contrastive=dict(negative_anchors_summary='Prior command failed',
        proposed_strategy='Inspect a different public source', orthogonality_proof=dict(
            dependency_dimension='Different dependency', target_dimension='Different file',
            command_dimension='A diagnostic rather than a failed check'),
        final_command=command_text(action), selected='A', candidates=rows))


class V9Tests(unittest.TestCase):
    def exercise(self, actions, env=None):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        actor = Scripted(actions); advisor = Scripted([])
        cfg = LeanConfig(max_turns=40, max_tools=30, contrastive_mode='orthogonal',
            memory_reliability=True, outcome_reliability=True, memory_decision=False,
            memory_injection=False, diagnostic_advisor_threshold=100,
            repeated_failure_threshold=100)
        env = env or FakeEnvironment()
        runner = LeanTaskRunner(env, actor, advisor, cfg, Path(tmp.name)/'audit')
        result = runner.run(TaskSpec('fixture', 'Fix the public task'))
        return result, read_trace(Path(tmp.name)/'audit/events.jsonl'), env, actor

    def test_gate_rejections_recover_with_one_counted_diagnostic(self):
        fail = run_action('fail')
        result, events, env, _ = self.exercise([fail, fail, fail, fail,
                                               run_action('write', 'fixed'), SUBMIT])
        self.assertTrue(result['submitted'], result)
        self.assertEqual(result['mechanism_utilization']['protocol_errors'], 0)
        self.assertEqual(result['mechanism_utilization']['contrastive_rejections'], 2)
        self.assertEqual(result['mechanism_utilization']['contrastive_diagnostic_fallbacks'], 1)
        self.assertEqual(result['tool_calls'], 3)  # failure + diagnostic + repair
        self.assertEqual(sum(a['argv'][0]=='fail' for a in env.executed), 1)
        self.assertEqual(len([e for e in events if e['event']=='action_loop_block']), 1)

    def test_prediction_selection_is_executed_and_observed(self):
        fail = run_action('fail')
        action = proposed(run_action('read', 'new.txt'), run_action('inspect', 'other.txt'))
        result, events, env, _ = self.exercise([fail, fail, action, SUBMIT])
        self.assertTrue(result['submitted'], result)
        self.assertEqual(result['mechanism_utilization']['contrastive_informative_predictions'], 1)
        outcome = next(e for e in events if e['event']=='contrastive_outcome')
        self.assertEqual(outcome['prediction'], 'supported_observation')
        self.assertTrue(outcome['new_evidence'])
        self.assertFalse(outcome['workspace_changed'])
        self.assertNotIn('inspect', [a['argv'][0] for a in env.executed])

    def test_repeated_reads_use_cached_result_until_workspace_changes(self):
        action=run_action('read', 'f.py')
        result, events, env, _ = self.exercise([action, action, action,
                                               run_action('artifact','f.py','repair'), action, SUBMIT])
        self.assertTrue(result['submitted'], result)
        self.assertEqual(result['mechanism_utilization']['action_loop_blocks'], 2)
        self.assertEqual(result['tool_calls'], 3)

    def test_spacing_cannot_bypass_last_boundary(self):
        a=run_action('bash','-lc','python check.py')
        b=run_action('bash','-lc','  python  "check.py"  ')
        result, _, _, _ = self.exercise([a,b,SUBMIT])
        self.assertEqual(result['tool_calls'],1)
        self.assertEqual(result['mechanism_utilization']['action_loop_blocks'],1)

    def test_external_recheck_claim_requires_observed_evidence(self):
        a=run_action('read','status')
        retry=dict(a,loop_retry=dict(reason='Service state may change',expected_change='READY appears'))
        result, _, _, _ = self.exercise([a,retry,retry,SUBMIT])
        self.assertEqual(result['tool_calls'],1)
        self.assertEqual(result['mechanism_utilization']['action_loop_blocks'],2)

    def test_compound_spacing_is_normalized_without_changing_quoted_data(self):
        a=run_action('bash','-lc','cd /app && cat f.py')
        b=run_action('bash','-lc','  cd   /app  &&  cat   f.py ')
        result, _, _, _ = self.exercise([a,b,SUBMIT])
        self.assertEqual(result['tool_calls'],1)
        a=run_action('bash','-lc',"echo 'a  b'")
        b=run_action('bash','-lc',"echo 'a b'")
        result, _, _, _ = self.exercise([a,b,SUBMIT])
        self.assertEqual(result['tool_calls'],2)

    def test_prediction_mismatch_falls_back_without_executing_hidden_candidate(self):
        fail=run_action('fail')
        wrong=proposed(run_action('read','new'),run_action('inspect','other'))
        wrong['contrastive']['selected']='B'
        result, _, env, _ = self.exercise([fail,fail,wrong,wrong,SUBMIT])
        self.assertTrue(result['submitted'],result)
        self.assertEqual(result['mechanism_utilization']['contrastive_rejections'],2)
        self.assertNotIn('inspect',[a['argv'][0] for a in env.executed])

    def test_incomplete_output_is_not_an_informative_prediction(self):
        class Incomplete(FakeEnvironment):
            def execute(self, action, deadline):
                result=super().execute(action,deadline)
                if action['argv'][0]=='read':
                    from dataclasses import replace
                    result=replace(result,output_truncated=True)
                return result
        action=proposed(run_action('read','new'),run_action('inspect','other'))
        result,events,_,_=self.exercise([run_action('fail'),run_action('fail'),action,SUBMIT],Incomplete())
        self.assertEqual(result['mechanism_utilization']['contrastive_informative_predictions'],0)
        self.assertEqual(result['mechanism_utilization']['contrastive_new_evidence'],0)

    def test_unrelated_edit_does_not_exempt_a_failed_check(self):
        from collections import Counter
        from bestfgs.contrastive_exploration import ContrastiveExploration
        from bestfgs.lean_memory import action_key
        class Gate(ContrastiveExploration):
            def _action_core(self,a):return a
            def _emit(self,*args,**kwargs):pass
        gate=Gate();gate.config=LeanConfig(contrastive_mode='orthogonal',memory_reliability=True,outcome_reliability=True)
        gate.counts=Counter();gate.environment=FakeEnvironment();gate._init_contrastive()
        action=run_action('pytest','config.json')
        gate.contrastive_visible_anchors=[dict(id='F1',command=command_text(action),
            command_key=action_key(action),dependencies={'config.json':'file:old'})]
        gate.environment.dependencies={'config.json':'file:old','notes.txt':'file:new'}
        gate.contrastive_episode=dict(id='X1',phase='plan')
        proposal=proposed(action,run_action('inspect','other'))
        blocked=gate._contrastive_before(proposal)
        self.assertTrue(blocked['not_executed'])
        gate.environment.dependencies['config.json']='file:fixed'
        audit=gate._contrastive_before(proposal)
        self.assertEqual(audit['condition_change_exemptions'],['F1'])

    def test_changed_cwd_and_stdin_are_distinct(self):
        a=run_action('read')
        result, _, _, _ = self.exercise([a,dict(a,cwd='other'),dict(a,stdin='different'),SUBMIT])
        self.assertEqual(result['tool_calls'],3)

    def test_public_check_change_is_verified_not_model_claim(self):
        class PublicEnvironment(FakeEnvironment):
            def execute(self, action, deadline):
                if action['argv'][0]=='pytest':
                    self.executed.append(action)
                    ok=self.value=='fixed'
                    return CommandResult(CommandSpec(tuple(action['argv']),'fixture'),
                        0 if ok else 1,'=== 1 passed in 0.1s ===' if ok else '=== 1 failed in 0.1s ===','',0)
                return super().execute(action,deadline)
        fail=run_action('pytest','config.json')
        repair=proposed(run_action('write','fixed'),run_action('inspect','other.txt'))
        retry=proposed(fail)
        retry['contrastive']['candidates'][0].update(supports='1 passed',refutes='1 failed')
        env=PublicEnvironment()
        # The environment declares the file changed by the repair; textual
        # "I repaired it" alone is insufficient to bypass the anchor.
        original=env.execute
        def execute(action,deadline):
            result=original(action,deadline)
            if action['argv'][0]=='write':env.dependencies['config.json']='file:fixed'
            return result
        env.execute=execute
        result, events, _, _ = self.exercise([fail,fail,repair,retry,SUBMIT],env)
        self.assertTrue(result['submitted'],result)
        self.assertEqual(result['mechanism_utilization']['contrastive_public_check_improvements'],1)
        self.assertEqual(result['mechanism_utilization']['contrastive_workspace_changes'],1)
        self.assertEqual(result['mechanism_utilization']['contrastive_informative_predictions'],1)

    def test_real_malformed_action_is_still_a_protocol_error(self):
        result, _, _, _ = self.exercise([{'action':'invalid'}]*3)
        self.assertEqual(result['stop_reason'],'model_or_protocol_error_limit')
        self.assertEqual(result['mechanism_utilization']['protocol_errors'],3)


if __name__=='__main__':unittest.main()
