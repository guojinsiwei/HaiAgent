import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'sources/bestfgs-project/src'),str(ROOT/'sources/bestfgs-project/tests')]
from bestfgs.terminal_text import clean_terminal, project_terminal
from bestfgs.prompt_views import compress_stream
from bestfgs.tool_outcomes import assess
from bestfgs.models import CommandResult, CommandSpec, TaskSpec
from bestfgs.lean_protocol import LeanConfig
from bestfgs.lean_runtime import LeanTaskRunner
from bestfgs.lean_audit import read_trace
from test_lean import FakeEnvironment, Scripted, SUBMIT, run_action


def result(stdout='',stderr='',code=0,argv=('python','-m','pytest')):
    return CommandResult(CommandSpec(argv,'fixture'),code,stdout,stderr,0)


class TerminalTests(unittest.TestCase):
    def test_plain_text_and_paths_are_unchanged(self):
        source = 'hello\tworld\n中文 C:\\temp\\a.py\n'
        self.assertEqual(clean_terminal(source),source)

    def test_color_and_cursor_codes_are_removed_not_executed(self):
        self.assertEqual(clean_terminal('\x1b[31mERROR\x1b[0m\x1b[2J\x1b[H\n'), 'ERROR\n')

    def test_osc_hyperlink_keeps_label_not_url(self):
        self.assertEqual(clean_terminal('\x1b]8;;https://example.invalid\x1b\\details\x1b]8;;\x1b\\'), 'details')

    def test_osc_bell_title_and_string_sequences(self):
        for sequence in ('\x1b]0;title\x07','\x1bPpayload\x1b\\','\x1b_payload\x1b\\',
                         '\x1b^payload\x1b\\','\x1bXpayload\x1b\\','\x1b(B'):
            with self.subTest(sequence=sequence):
                self.assertEqual(clean_terminal('a'+sequence+'b'),'ab')

    def test_eight_bit_control_sequences(self):
        self.assertEqual(clean_terminal('\x9b31merror\x9b0m\x9dtitle\x9c'),'error')

    def test_crlf_is_one_line_and_refreshes_preserve_prior_errors(self):
        self.assertEqual(clean_terminal('error\rprogress\r100%\r\n'), 'error\nprogress\n100%\n')

    def test_backspace_does_not_erase_observed_error_text(self):
        self.assertEqual(clean_terminal('ERROR\b\b\b\b\bOK'),'ERROROK')

    def test_unterminated_controls_are_marked_not_silent(self):
        for source in ('\x1b','\x1b]unfinished','\x1b[31'):
            with self.subTest(source=source):
                clean,view = project_terminal(source)
                self.assertTrue(view['incomplete'])
                self.assertIn('projection may omit text',clean)
                self.assertNotIn('\x1b',clean)

    def test_compression_preserves_diagnostic_budget(self):
        source = ('\x1b[32mprogress\x1b[0m\r'*500)+'\x1b[31mValueError: mismatch\x1b[0m\n'
        view = compress_stream(source,'test',1000)
        self.assertLessEqual(len(view),1000)
        self.assertNotIn('\x1b',view)
        self.assertIn('ValueError: mismatch',view)

    def test_colored_traceback_is_still_a_warning_on_zero_exit(self):
        status = assess(result(stderr='\x1b[31mTraceback (most recent call last):\nValueError: bad\x1b[0m\n'))
        self.assertTrue(status['suspected_failure'])
        self.assertFalse(status['execution_clean'])

    def test_colored_public_summary_remains_readable(self):
        self.assertEqual(assess(result(stdout='\x1b[32m=== 1 passed in 0.1s ===\x1b[0m\n'))['check_status'],'public_check_passed')

    def test_incomplete_projection_cannot_claim_public_check_passed(self):
        status = assess(result(stdout='=== 1 passed in 0.1s ===\n\x1b]unfinished'))
        self.assertEqual(status['check_status'],'unknown')
        self.assertIn('terminal_control_incomplete',status['signals'])

    def test_outcome_assessment_does_not_mutate_original(self):
        original = result(stdout='\x1b[32m=== 1 passed in 0.1s ===\x1b[0m\n')
        before = copy.deepcopy(original)
        assess(original)
        self.assertEqual(original,before)


class ColorEnvironment(FakeEnvironment):
    def execute(self,action,deadline):
        self.executed.append(action)
        return result(stdout='\x1b[32mraw output\x1b[0m\rrefresh\n',argv=tuple(action['argv']))


class RuntimeAndHandoverTests(unittest.TestCase):
    def exercise(self,actions,advisor=(),env=None,**overrides):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        cfg = LeanConfig(**(dict(max_turns=30,max_tools=20,max_advisor_calls=1,
            advisor_cooldown_tools=1,diagnostic_nudge_threshold=20,diagnostic_advisor_threshold=21)|overrides))
        actor,guide = Scripted(actions),Scripted(advisor)
        runner = LeanTaskRunner(env or FakeEnvironment(),actor,guide,cfg,Path(temp.name)/'audit',monitor_client=Scripted([]))
        output = runner.run(TaskSpec('fixture','Fix parser and preserve requested behavior'))
        self.assertIsNone(output['error_type'],output)
        return runner,actor,guide,read_trace(Path(temp.name)/'audit/events.jsonl')

    def test_raw_audit_remains_while_model_and_history_are_clean(self):
        _,actor,_,events = self.exercise([run_action('read'),SUBMIT],env=ColorEnvironment())
        raw = next(e for e in events if e['event']=='tool_call')['result']['stdout']
        self.assertIn('\x1b',raw)
        self.assertNotIn('\x1b',json.dumps(actor.prompts[-1],ensure_ascii=False))
        history = next(e for e in events if e['event']=='conversation_turn')
        self.assertNotIn('\x1b',history['feedback']['evidence']['stdout'])
        self.assertIn('raw output\nrefresh',history['feedback']['evidence']['stdout'])
        self.assertTrue(any(e['event']=='terminal_projection' for e in events))

    def test_report_has_three_actual_failed_attempts_and_reaches_advisor(self):
        runner,_,guide,events = self.exercise([run_action('fail','A'),run_action('fail','B'),run_action('fail','C'),
            dict(action='consult',question='Which input condition should be checked next?'),SUBMIT],advisor=[dict(alternatives=[])])
        report = guide.prompts[0]['handover_report']
        self.assertEqual(len(report['failed_attempts']),3)
        self.assertEqual(report['advertised_evidence_ids'],['E1','E2','E3'])
        self.assertEqual(report['latest_problem']['return_code'],1)
        self.assertFalse(report['latest_problem']['current_failure_confirmed'])
        self.assertLessEqual(len(json.dumps(report,ensure_ascii=False)),6000)
        self.assertTrue((runner.output/'latest-handover.json').exists())
        self.assertLess(next(i for i,e in enumerate(events) if e['event']=='advisor_handover'),
                        next(i for i,e in enumerate(events) if e['event']=='model_request' and e['role']=='advisor'))

    def test_report_does_not_invent_three_solutions_or_call_extra_model(self):
        _,_,guide,_ = self.exercise([run_action('fail'),dict(action='consult',question='Need a new check'),SUBMIT],
            advisor=[dict(alternatives=[])])
        report = guide.prompts[0]['handover_report']
        self.assertEqual(len(report['failed_attempts']),1)
        self.assertEqual(report['distinct_failed_attempts_observed'],1)
        self.assertEqual(len(guide.prompts),1)

    def test_report_written_even_if_guide_budget_is_unavailable(self):
        runner,_,guide,events = self.exercise([dict(action='consult',question='Need help'),SUBMIT],max_advisor_calls=0)
        self.assertTrue((runner.output/'latest-handover.json').exists())
        self.assertEqual(guide.prompts,[])
        report = next(e for e in events if e['event']=='advisor_handover')['report']
        self.assertEqual(report['failed_attempts'],[])

    def test_older_failed_attempt_in_report_is_valid_advice_evidence(self):
        advice = dict(alternatives=[dict(hypothesis='Recorded error needs a changed input',
            check='Inspect input encoding',difference='Inspect rather than repeat',evidence_ids=['E1'])])
        runner,_,guide,_ = self.exercise([run_action('fail')]+[run_action('read',str(i)) for i in range(8)]+
            [dict(action='consult',question='Explain the earlier failure'),SUBMIT],advisor=[advice])
        self.assertNotIn('E1',{e['id'] for e in guide.prompts[0]['fixed_context']['evidence']})
        self.assertIn('E1',guide.prompts[0]['handover_report']['advertised_evidence_ids'])
        self.assertEqual(runner.counts['advisor_responses_accepted'],1)


if __name__ == '__main__': unittest.main()
