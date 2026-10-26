from dataclasses import replace
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from terminal_context import TaskContext, TerminalEvent, Limits
from terminal_context.stagnation import RepetitionTracker
from haiagent.demo import ScriptedClient
from haiagent.executor import Result
from haiagent.protocol import Config, Task
from haiagent.runtime import run
from haiagent.storage import read_trace


class StagnationTests(unittest.TestCase):
    def event(self, **kwargs):
        return replace(TerminalEvent('T', 'bash -lc \'ocr image | grep total\'',
            stdout='invoice 123', exit_code=0, cwd='/app', workspace='W', workspace_before='W',
            input_digest=hashlib.sha256(b'').hexdigest()), **kwargs)

    def test_zero_exit_repetition_creates_one_evidenced_memory_and_prompt_advice(self):
        c=TaskContext('T', 'extract invoice')
        for _ in range(5): c.observe(self.event(strategy='OCR then grep invoice total'))
        snap=c.snapshot()
        self.assertEqual(len(snap['memories']),1)
        self.assertEqual(len(snap['strategies']),1)
        self.assertEqual(snap['strategies'][0]['attempts'],5)
        self.assertEqual(snap['strategies'][0]['status'],'stalled_exact_repeat')
        self.assertEqual(snap['memories'][0]['validity'],'unknown')
        p=json.loads(c.build_prompt(include_feedback=False).content)
        self.assertEqual(p['decision_advice']['count'],5)
        self.assertTrue(p['task_memory'])
        self.assertEqual(p['exploration_history'][0]['strategy'],'OCR then grep invoice total')
        self.assertIn('not proof',p['decision_advice']['observation'])

    def test_incomplete_and_timeouts_never_claim_identical_output(self):
        for changes in ({'output_truncated':True},{'timed_out':True},{'blocked':True}, {'exit_code':None}):
            c=TaskContext('T','extract')
            for _ in range(5): c.observe(self.event(**changes))
            self.assertNotIn('decision_advice',json.loads(c.build_prompt().content))

    def test_changed_output_resets_and_modified_workspace_is_not_stagnation(self):
        c=TaskContext('T','extract')
        for _ in range(3): c.observe(self.event())
        c.observe(self.event(stdout='new invoice'))
        self.assertNotIn('decision_advice',json.loads(c.build_prompt().content))
        for _ in range(4): c.observe(self.event(workspace_before='old'))
        self.assertNotIn('decision_advice',json.loads(c.build_prompt().content))

    def test_scope_and_stdin_changes_reset_matching(self):
        for changes in ({'cwd':'/other'}, {'workspace':'W2','workspace_before':'W2'},
                        {'environment':'new'}, {'input_digest':'new-input'}):
            c=TaskContext('T','extract')
            for _ in range(3): c.observe(self.event())
            c.observe(self.event(**changes))
            self.assertNotIn('decision_advice',json.loads(c.build_prompt().content))

    def test_tracker_capacity_is_bounded(self):
        t=RepetitionTracker(capacity=4)
        for i in range(100): t.observe(self.event(command='echo '+str(i)), 'E'+str(i), True)
        self.assertEqual(len(t.entries),4)

    def test_rolling_subgoals_are_observational_bounded_and_prompt_visible(self):
        c=TaskContext('T','extract',limits=Limits(subgoal_count=2))
        c.observe(self.event(strategy='inspect logs',subgoal='locate failing stage'))
        c.observe(self.event(command='edit parser',stdout='changed',strategy='patch parser',
                             subgoal='implement narrow repair',workspace_before='old'))
        snap=c.snapshot()
        self.assertEqual([g['subgoal'] for g in snap['subgoals']],
                         ['locate failing stage','implement narrow repair'])
        self.assertEqual(snap['subgoals'][0]['status'],'suspended_unverified')
        self.assertEqual(snap['subgoals'][1]['status'],'active')
        self.assertEqual(snap['subgoals'][1]['workspace_changes'],1)
        self.assertNotIn('completed',json.dumps(snap['subgoals']))
        prompt=json.loads(c.build_prompt(include_feedback=False).content)
        self.assertEqual(prompt['task_progress']['subgoals'][-1]['subgoal'],
                         'implement narrow repair')
        self.assertIn('does not mean completed',prompt['task_progress']['semantics'])

    def test_repeat_marks_current_subgoal_stalled_without_extra_model_call(self):
        c=TaskContext('T','extract')
        for _ in range(3):
            c.observe(self.event(strategy='inspect logs',subgoal='locate failing stage'))
        repeated=c.repeat_advice(self.event().command,'/app',self.event().input_digest)
        recovery=c.repetition_recovery('inspect logs',repeated,blocked_count=1,
                                       subgoal='locate failing stage')
        self.assertEqual(recovery['current_subgoal']['status'],'stalled_exact_repeat')
        self.assertIn('Keep the same subgoal',recovery['required_change'])

    def test_interleaved_actions_retain_repetition_without_guessing_equivalence(self):
        c=TaskContext('T','extract')
        for _ in range(3):
            c.observe(self.event())
            c.observe(self.event(command='different command',stdout='other'))
        self.assertTrue(c.repeat_advice(self.event().command,'/app',self.event().input_digest))
        self.assertIsNone(c.repeat_advice('ocr alternate spelling','/app',self.event().input_digest))

    def test_tiny_recent_storage_keeps_detector_bounded_and_live_evidence(self):
        c=TaskContext('T','extract',limits=Limits(recent_bytes=2))
        for _ in range(5): c.observe(self.event())
        self.assertEqual(len(c.snapshot()['memories']),1)
        self.assertTrue(c.snapshot()['memories'][0]['evidence'])

    def run_case(self, method='hai', retry_reason=None):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        root=Path(tmp.name);ws=root/'ws';ws.mkdir()
        action={'action':'run','argv':['bash','-lc','ocr image | grep total'],
                'strategy':'OCR then grep invoice total'}
        fourth=dict(action)
        if retry_reason: fourth['retry_reason']=retry_reason
        client=ScriptedClient([action]*3+[fourth,{'action':'submit','summary':'done'}])
        class Exec:
            def execute(self,*args): return Result(0,stdout='same invoice')
        result=run(Task('T','extract invoice',ws,delivery='terminal'),Config(method=method),client,root/'out',executor=Exec())
        return result,client,read_trace(root/'out/events.jsonl')

    def test_semantic_memory_preempts_unexplained_soft_exact_retry(self):
        result,client,trace=self.run_case()
        self.assertTrue(result['submitted'])
        self.assertEqual(result['tool_calls'],3)
        self.assertEqual(result['interaction_rounds'],5)
        context=json.loads(client.requests[4][1]['content'])['context']
        self.assertTrue(context['memory_intervention'])
        self.assertTrue(any(e['event']=='automatic_memory' for e in trace))
        self.assertEqual(sum(e['event']=='memory_intervention' for e in trace),1)
        self.assertFalse(any(e['event']=='repeat_decision' for e in trace))

    def test_new_strategy_after_repeat_is_executed_and_audited(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        root=Path(tmp.name);ws=root/'ws';ws.mkdir()
        repeated={'action':'run','argv':['bash','-lc','ocr image | grep total'],
                  'strategy':'OCR then grep invoice total'}
        alternative={'action':'run','argv':['python','watershed.py'],
                     'strategy':'Watershed overlapping regions',
                     'subgoal':'separate overlapping cells'}
        client=ScriptedClient([repeated]*4+[alternative,{'action':'submit','summary':'done'}])
        class Exec:
            def execute(self,*args): return Result(0,stdout='same invoice')
        result=run(Task('T','extract invoice',ws,delivery='terminal'),Config(),client,root/'out',executor=Exec())
        trace=read_trace(root/'out/events.jsonl')
        self.assertTrue(result['submitted'])
        self.assertEqual(result['tool_calls'],4)
        self.assertEqual(sum(e['event']=='memory_intervention' for e in trace),1)
        reconsideration=next(e for e in trace if e['event']=='memory_reconsideration')
        self.assertTrue(reconsideration['changed_direction'])
        self.assertTrue(reconsideration['changed_action'])
        self.assertTrue(any(e['event']=='memory_followup_outcome' and
                            e['action_kind']=='run' for e in trace))
        strategies=[e['strategy']['strategy'] for e in trace if e['event']=='strategy_observed']
        self.assertIn('Watershed overlapping regions',strategies)
        subgoals=[e['subgoal']['subgoal'] for e in trace if e['event']=='subgoal_observed']
        self.assertIn('separate overlapping cells',subgoals)

    def test_repeated_blocked_decision_has_bounded_stagnation_stop(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        root=Path(tmp.name);ws=root/'ws';ws.mkdir()
        action={'action':'run','argv':['bash','-lc','ocr image | grep total'],
                'strategy':'OCR then grep invoice total'}
        client=ScriptedClient([action]*8)
        class Exec:
            def execute(self,*args): return Result(0,stdout='same invoice')
        result=run(Task('T','extract invoice',ws,delivery='terminal'),
                   Config(max_repeat_blocks=3),client,root/'out',executor=Exec())
        trace=read_trace(root/'out/events.jsonl')
        self.assertEqual(result['stop_reason'],'stagnation_limit')
        self.assertEqual(result['tool_calls'],3)
        self.assertEqual(result['interaction_rounds'],6)
        self.assertEqual(sum(e['event']=='memory_intervention' for e in trace),3)
        self.assertEqual(sum(e['event']=='memory_reconsideration' for e in trace),2)
        self.assertFalse(any(e['event']=='repeat_decision' for e in trace))

    def test_explained_polling_is_allowed(self):
        result,_,trace=self.run_case(retry_reason='Poll the asynchronous producer once more before trying a different source.')
        self.assertEqual(result['tool_calls'],4)
        self.assertTrue(next(e for e in trace if e['event']=='repeat_decision')['executed'])

    def test_explained_retries_are_bounded_and_cannot_reset_loop_forever(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        root=Path(tmp.name);ws=root/'ws';ws.mkdir()
        action={'action':'run','argv':['bash','-lc','ocr image | grep total'],
                'strategy':'OCR then grep invoice total',
                'retry_reason':'Poll the asynchronous producer once more before changing information source.'}
        client=ScriptedClient([action]*12)
        class Exec:
            def execute(self,*args): return Result(0,stdout='same invoice')
        result=run(Task('T','extract invoice',ws,delivery='terminal'),
                   Config(max_repeat_blocks=3,max_explained_retries=2),
                   client,root/'out',executor=Exec())
        trace=read_trace(root/'out/events.jsonl')
        self.assertEqual(result['stop_reason'],'stagnation_limit')
        self.assertEqual(result['tool_calls'],5)
        reviews=[e for e in trace if e['event']=='repeat_decision']
        self.assertEqual(sum(e['executed'] for e in reviews),2)
        self.assertEqual(sum(not e['executed'] for e in reviews),0)
        self.assertEqual(sum(e['event']=='memory_override_reason_exhausted'
                             for e in trace),3)
        self.assertEqual(sum(e['event']=='memory_intervention' for e in trace),3)

    def test_raw_behavior_unchanged(self):
        result,_,trace=self.run_case(method='raw')
        self.assertEqual(result['tool_calls'],4)
        self.assertFalse(any(e['event'] in ('automatic_memory','repeat_decision') for e in trace))
