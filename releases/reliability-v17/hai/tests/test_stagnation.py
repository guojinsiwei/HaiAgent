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
        for _ in range(5): c.observe(self.event())
        snap=c.snapshot()
        self.assertEqual(len(snap['memories']),1)
        self.assertEqual(snap['memories'][0]['validity'],'unknown')
        p=json.loads(c.build_prompt(include_feedback=False).content)
        self.assertEqual(p['decision_advice']['count'],5)
        self.assertTrue(p['task_memory'])
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
        action={'action':'run','argv':['bash','-lc','ocr image | grep total']}
        fourth=dict(action)
        if retry_reason: fourth['retry_reason']=retry_reason
        client=ScriptedClient([action]*3+[fourth,{'action':'submit','summary':'done'}])
        class Exec:
            def execute(self,*args): return Result(0,stdout='same invoice')
        result=run(Task('T','extract invoice',ws,delivery='terminal'),Config(method=method),client,root/'out',executor=Exec())
        return result,client,read_trace(root/'out/events.jsonl')

    def test_runtime_requires_reason_before_fourth_repeat_without_hidden_call(self):
        result,client,trace=self.run_case()
        self.assertTrue(result['submitted'])
        self.assertEqual(result['tool_calls'],3)
        self.assertEqual(result['interaction_rounds'],5)
        self.assertTrue(json.loads(client.requests[3][1]['content'])['context']['decision_advice'])
        self.assertTrue(any(e['event']=='automatic_memory' for e in trace))
        review=next(e for e in trace if e['event']=='repeat_decision')
        self.assertFalse(review['executed'])

    def test_explained_polling_is_allowed(self):
        result,_,trace=self.run_case(retry_reason='Poll the asynchronous producer once more before trying a different source.')
        self.assertEqual(result['tool_calls'],4)
        self.assertTrue(next(e for e in trace if e['event']=='repeat_decision')['executed'])

    def test_raw_behavior_unchanged(self):
        result,_,trace=self.run_case(method='raw')
        self.assertEqual(result['tool_calls'],4)
        self.assertFalse(any(e['event'] in ('automatic_memory','repeat_decision') for e in trace))
