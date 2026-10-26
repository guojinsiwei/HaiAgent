"""Read-only historical replay: verifies observation trigger, not a model outcome."""
import hashlib
import json
from pathlib import Path
import shlex
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / 'project/src'))
from terminal_context import TaskContext, TerminalEvent

old = Path('/mnt/sdb/home/lizh639/hai-terminal6-v030-20260926/runs/01-financial-document-processor-hai')
paths = list(old.glob('*/agent/haia-run/events.jsonl'))
assert len(paths) == 1
events = [json.loads(line) for line in paths[0].read_text().splitlines()]
task = next(e['task_id'] for e in events if e['event'] == 'header')
context = TaskContext(task, 'Replay observations only')
pending, triggered = {}, []
for event in events:
    if event['event'] == 'tool_start':
        pending[event['call_id']] = event
    if event['event'] != 'tool_end':
        continue
    start = pending[event['call_id']]
    decision, result = start['command'], event['result']
    feedback = context.observe(TerminalEvent(task_id=task, command=shlex.join(decision['argv']),
        cwd=str(Path('/app') / decision['cwd']), workspace=event['after_revision'],
        workspace_before=start['before_revision'], environment=None,
        stdout=result['stdout'], stderr=result['stderr'], exit_code=result['exit_code'],
        timed_out=result['timed_out'], blocked=result['blocked'], output_truncated=result['output_truncated'],
        input_digest=hashlib.sha256((decision.get('stdin') or '').encode()).hexdigest()))
    if feedback.get('repetition'):
        view = json.loads(context.build_prompt(include_feedback=False).content)
        assert view.get('decision_advice')
        triggered.append({'call_id': event['call_id'], 'count': feedback['repetition']['count'],
                          'memory_id': feedback['repetition']['memory_id'],
                          'advice_visible': True})
assert triggered, 'Real repeated-output trace failed to create advice'
print(json.dumps({'historical_trace_sha256': hashlib.sha256(paths[0].read_bytes()).hexdigest(),
                  'first_trigger': triggered[0], 'trigger_count': len(triggered),
                  'model_calls': 0, 'not_a_counterfactual_success_claim': True}))
