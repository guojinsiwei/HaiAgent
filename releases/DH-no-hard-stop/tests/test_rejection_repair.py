"""No API: exercise the actual runner, gate combination and executable diagnostic."""
from dataclasses import replace
import json
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'sources/bestfgs-project/src'), str(ROOT/'sources/bestfgs-project/tests')]
from bestfgs.lean_protocol import LeanConfig
from bestfgs.lean_runtime import LeanTaskRunner
from bestfgs.lean_audit import read_trace
from bestfgs.models import TaskSpec
from bestfgs.rejection_recovery import RejectionRecovery
from bestfgs.targeted_diagnostics import diagnostic_action, diagnostic_plan
from test_lean import FakeEnvironment, Scripted, run_action, SUBMIT
from test_contrastive_exploration import orthogonal_action
from bestfgs.lean_environment import LiveWorkspace


class RelatedEnvironment(FakeEnvironment):
    def __init__(self):
        super().__init__()
        self.dependencies = {'f.py': 'file:old', 'config.json': 'file:old'}

    def contrastive_dependencies(self, action):
        return ['f.py', 'config.json'] if action['argv'][0] in ('fail', 'check') else []

    def execute(self, action, deadline):
        result = super().execute(action, deadline)
        if action['argv'][0] == 'grep':
            return replace(result, stdout='f.py:14: specific new fact')
        if action['argv'][0] == 'ls':
            return replace(result, stdout='f.py config.json')
        return result


class RejectionRepairTests(unittest.TestCase):
    def exercise(self, actions, *, env=None, advice=None, **overrides):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        options = dict(max_turns=80, max_tools=60, contrastive_mode='orthogonal',
            contrastive_predictions=False, memory_reliability=True, outcome_reliability=True,
            memory_decision=False, memory_injection=False,
            diagnostic_advisor_threshold=100, repeated_failure_threshold=100)
        options.update(overrides)
        actor = Scripted(actions)
        advisor = Scripted(advice if advice is not None else [dict(alternatives=[])]*10)
        runner = LeanTaskRunner(env or RelatedEnvironment(), actor, advisor,
                               LeanConfig(**options), Path(tmp.name)/'audit')
        result = runner.run(TaskSpec('recovery', 'Fix f.py'))
        events = read_trace(Path(tmp.name)/'audit/events.jsonl')
        self.assertNotEqual(result['stop_reason'], 'infrastructure_error', result)
        return result, events, runner

    def test_rejections_beyond_fourteen_do_not_stop_submission(self):
        result, events, runner = self.exercise([run_action('read','f.py')]*40+[SUBMIT])
        self.assertEqual(result['stop_reason'], 'model_submit')
        self.assertEqual(result['tool_calls'], 1)
        self.assertEqual(result['advisor_rounds'], 1)
        self.assertEqual(result['action_rounds'], 41)
        self.assertEqual(result['mechanism_utilization']['recovery_rejected_turns'], 39)
        self.assertIsNotNone(result['artifact'])
        self.assertEqual(runner.environment.deliveries, 1)
        self.assertTrue(result['submitted'])
        self.assertFalse(any(e['event']=='recovery_exhausted' for e in events))
        self.assertFalse(runner.rejection_recovery.view()['hard_stop_enabled'])
        trigger = next(i for i,e in enumerate(events) if e['event']=='advisor_trigger')
        self.assertEqual(sum(e['event']=='recovery_rejection' for e in events[:trigger]), 7)

    def test_mixed_gates_and_cached_diagnostic_cannot_reset_count(self):
        result, events, runner = self.exercise([run_action('fail','f.py')]*50+[SUBMIT])
        self.assertEqual(result['stop_reason'], 'model_submit')
        rejects = [e for e in events if e['event']=='recovery_rejection']
        self.assertGreater(len(rejects), 14)
        self.assertTrue(any('action_loop' in e['sources'] for e in rejects))
        self.assertTrue(any('contrastive_rejection' in e['sources'] for e in rejects))
        self.assertEqual(result['advisor_rounds'], 1)
        diagnostics = [a for a in runner.environment.executed if a['argv'][0]=='python3']
        self.assertEqual(len(diagnostics), 1)

    def test_listing_and_unrelated_edit_do_not_reset(self):
        action = run_action('read','f.py')
        result, events, runner = self.exercise([action]*7+[run_action('ls','f.py'),
            run_action('artifact','notes.txt','changed'),action,SUBMIT])
        self.assertTrue(result['submitted'])
        self.assertEqual(result['advisor_rounds'],1)
        self.assertEqual(result['mechanism_utilization'].get('recovery_progress_resets',0),0)
        self.assertEqual(sum(a['argv']==['read','f.py'] for a in runner.environment.executed),1)

    def test_related_edit_resets_and_original_command_runs(self):
        action=run_action('read','f.py')
        result, events, runner=self.exercise([action]*7+[run_action('artifact','f.py','new'),action,SUBMIT])
        self.assertTrue(result['submitted'])
        self.assertEqual(result['advisor_rounds'],0)
        self.assertEqual(result['mechanism_utilization']['recovery_progress_resets'],1)
        self.assertEqual(sum(a['argv']==['read','f.py'] for a in runner.environment.executed),2)

    def test_targeted_new_evidence_resets_but_same_output_does_not(self):
        action=run_action('read','f.py')
        result, events, _=self.exercise([action]*7+[run_action('grep','specific','f.py'),action,SUBMIT])
        self.assertTrue(result['submitted'])
        self.assertEqual(result['advisor_rounds'],0)
        self.assertEqual(result['mechanism_utilization']['recovery_progress_resets'],1)

    def test_relevant_config_change_allows_failed_check_without_proof(self):
        action=run_action('fail','f.py')
        result, events, runner=self.exercise([action,action,
            orthogonal_action(run_action('artifact','config.json','new')),action,SUBMIT])
        self.assertTrue(result['submitted'],result)
        self.assertEqual(sum(a['argv']==['fail','f.py'] for a in runner.environment.executed),2)
        self.assertTrue(any(e['event']=='contrastive_validation' and
            e.get('audit',{}).get('condition_change_exemptions') for e in events))

    def test_claimed_external_change_does_not_bypass(self):
        a=run_action('read','f.py')
        claim=dict(a,loop_retry=dict(reason='I changed it',expected_change='passes now'))
        result,_,_=self.exercise([a,claim,SUBMIT])
        self.assertEqual(result['tool_calls'],1)

    def test_total_model_budget_still_limits_advisor_and_actor(self):
        result,_,_=self.exercise([run_action('read','f.py')]*30,max_turns=9)
        self.assertEqual(result['interaction_rounds'],9)
        self.assertEqual(result['advisor_rounds'],1)
        self.assertEqual(result['stop_reason'],'model_budget')

    def test_disabled_advisor_does_not_stop_submission(self):
        result,events,_=self.exercise([run_action('read','f.py')]*30+[SUBMIT],max_advisor_calls=0)
        self.assertEqual(result['stop_reason'],'model_submit')
        self.assertEqual(result['advisor_rounds'],0)
        self.assertTrue(any(e['event']=='advisor_skipped' for e in events))

    def test_rejections_still_obey_original_request_budget(self):
        result,events,runner=self.exercise([run_action('read','f.py')]*100,max_turns=40)
        self.assertEqual(result['stop_reason'],'model_budget')
        self.assertEqual(result['interaction_rounds'],40)
        self.assertEqual(result['advisor_rounds'],1)
        self.assertEqual(runner.environment.deliveries,1)
        self.assertFalse(any(e['event']=='recovery_exhausted' for e in events))

    def test_disabled_advisor_still_obeys_request_budget(self):
        result,events,_=self.exercise([run_action('read','f.py')]*100,max_turns=40,max_advisor_calls=0)
        self.assertEqual(result['stop_reason'],'model_budget')
        self.assertEqual(result['interaction_rounds'],40)
        self.assertEqual(result['advisor_rounds'],0)
        self.assertEqual(sum(e['event']=='advisor_skipped' for e in events),1)

    def test_real_progress_starts_a_new_seven_budget(self):
        a=run_action('read','f.py')
        result,events,_=self.exercise([a]*8+[run_action('artifact','f.py','fixed')]+[a]*8+[SUBMIT])
        self.assertTrue(result['submitted'])
        self.assertEqual(result['advisor_rounds'],2)

    def test_last_advisor_slot_is_reserved_and_rescue_bypasses_cooldown(self):
        a=run_action('read','f.py')
        result,events,_=self.exercise([dict(action='consult',question='What next?')]+[a]*8+[SUBMIT],
                                      max_advisor_calls=1,advisor_cooldown_tools=1000)
        self.assertTrue(result['submitted'])
        self.assertEqual(result['advisor_rounds'],1)
        triggers=[e for e in events if e['event']=='advisor_trigger']
        self.assertEqual([e['trigger'] for e in triggers],['seven_rejections'])

    @unittest.skipUnless(os.name=='posix','Actual executor requires POSIX process groups')
    def test_real_traceback_imported_file_repair_and_same_test(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);seed=root/'seed';seed.mkdir()
            (seed/'test.py').write_text('from impl import answer\nassert answer == 2\n')
            (seed/'impl.py').write_text('raise ValueError("broken import")\n')
            env=LiveWorkspace(seed,root/'run')
            test=run_action(sys.executable,'-B','test.py')
            edit=orthogonal_action(run_action(sys.executable,'-c',
                'from pathlib import Path;Path("impl.py").write_text("answer = 2\\n")'))
            result,events,runner=self.exercise([test,test,edit,test,SUBMIT],env=env)
            self.assertTrue(result['submitted'],result)
            outputs=[e for e in events if e['event']=='tool_call']
            self.assertEqual(result['tool_calls'],3)
            self.assertEqual((env.workspace/'impl.py').read_text(),'answer = 2\n')
            self.assertTrue(any(e['event']=='contrastive_validation' and
                e.get('audit',{}).get('condition_change_exemptions') for e in events))


class DiagnosticTests(unittest.TestCase):
    def run_diagnostic(self, root, anchors):
        a=diagnostic_action(anchors)
        p=subprocess.run([sys.executable,*a['argv'][1:]],input=a['stdin'],text=True,
                         capture_output=True,cwd=root,timeout=15)
        self.assertEqual(p.returncode,0,p.stderr)
        return json.loads(p.stdout)

    def test_deep_qualified_symbol_not_first_file_header(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'ants.py').write_text('# padding\n'*500+
                'class Other:\n    def action(self):\n        return "wrong"\n'+
                'class QueenAnt:\n    def action(self):\n        return "target"\n')
            anchors=[dict(dependencies={'ants.py':'file:old','QueenAnt.action':'missing'},observation='')]
            plan=diagnostic_plan(anchors)
            self.assertEqual(plan['files'],['ants.py'])
            self.assertIn('QueenAnt.action',plan['symbols'])
            out=self.run_diagnostic(root,anchors)
            self.assertFalse(out['no_match'])
            self.assertTrue(any(x['reason']=='symbol QueenAnt.action' and 'target' in x['text'] for x in out['excerpts']))

    def test_traceback_line_has_priority(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'a.py').write_text('\n'*299+'raise ValueError("HERE")\n')
            out=self.run_diagnostic(root,[dict(dependencies={},observation='File "/app/a.py", line 300, in run')])
            self.assertIn('HERE',out['excerpts'][0]['text'])
            self.assertEqual(out['excerpts'][0]['reason'],'observed error line')

    def test_missing_path_searches_symbol_and_outside_path_is_ignored(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'nested').mkdir();(root/'nested/real.py').write_text('def target():\n    return 1\n')
            out=self.run_diagnostic(root,[dict(dependencies={'missing.py':'missing'},
                observation='File "../../secret.py", line 1, in target')])
            self.assertTrue(any(x['path']=='nested/real.py' for x in out['excerpts']))
            self.assertFalse(any('secret' in x['path'] for x in out['excerpts']))

    def test_unresolved_symbol_reports_no_match_instead_of_header(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'a.py').write_text('SECRET_HEADER=1\n')
            out=self.run_diagnostic(root,[dict(dependencies={'a.py':'file:old','Unknown.method':'missing'},observation='')])
            self.assertTrue(out['no_match'])
            self.assertEqual(out['excerpts'],[])


if __name__=='__main__':
    unittest.main()
