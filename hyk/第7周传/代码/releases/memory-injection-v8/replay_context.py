"""Offline replay of frozen model-request states; no API, tools or Docker."""
import copy
import json
from collections import OrderedDict, Counter
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT/'sources/bestfgs-project/src'), str(ROOT/'sources/bestfgs-project/tests')]
from bestfgs.lean_runtime import LeanTaskRunner
from bestfgs.lean_protocol import LeanConfig
from bestfgs.lean_audit import atomic_json
from bestfgs.lean_conversation import Conversation, message_chars
from bestfgs.lean_memory import Memories
from bestfgs.lean_progress import DeliveryProgress
from bestfgs.models import TaskSpec
from test_lean import Scripted, FakeEnvironment, SUBMIT


class Capture(Scripted):
    def __init__(self, responses):
        super().__init__(responses); self.calls = []
    def complete_json(self, **kwargs):
        self.calls.append(copy.deepcopy(kwargs))
        return super().complete_json(**kwargs)


class SnapshotEnvironment(FakeEnvironment):
    def __init__(self):
        super().__init__(); self.fingerprint = 'snapshot'
    def scope(self): return self.fingerprint


def replay(path):
    memories, evidence, conversation = OrderedDict(), OrderedDict(), Conversation()
    counters, examples = Counter(), []
    tools = 0
    with tempfile.TemporaryDirectory() as temp:
        env = SnapshotEnvironment()
        runner = LeanTaskRunner(env, Scripted([SUBMIT]), Scripted([]),
            LeanConfig(memory_reliability=True, max_advisor_calls=0), Path(temp)/'initial')
        runner.run(TaskSpec('initial', 'initialize state only'))
        for line in Path(path).open(encoding='utf-8'):
            event = json.loads(line); name = event['event']
            if name == 'memory_admitted':
                memories[event['memory']['id']] = event['memory']
            elif name == 'memory_evicted':
                memories.pop(event.get('id', event.get('memory_id')), None)
            elif name == 'tool_call':
                tools += 1
                result, command = event['result'], event['command']
                row = dict(id=event['evidence_id'], argv=json.dumps(command['argv']),
                    purpose=command.get('purpose', ''), stdout=result['stdout'], stderr=result['stderr'],
                    before=event['before'], after=event['after'], return_code=result['return_code'],
                    timed_out=result.get('timed_out', False), blocked=result.get('blocked', False))
                evidence[row['id']] = row
                env.dependencies.update(event.get('dependency_after', {}))
            elif name == 'conversation_turn':
                conversation.append(event['action'], event['feedback'], event.get('context'))
            elif name == 'model_request' and event.get('role') == 'action':
                old = event['payload']; panel = old['fixed_context']
                runner.task = TaskSpec(**old['task'])
                env.fingerprint = panel['current_workspace']
                # Exact captured dependencies where available; never infer a
                # current success from an old memory's dependency snapshot.
                runner.memory = Memories(reliable=True)
                runner.memory.items = copy.deepcopy(memories)
                runner.evidence = copy.deepcopy(evidence)
                # The original request's surviving evidence is already the exact
                # runtime dashboard view (not the full stdout in tool_call).
                for row in panel['evidence']:
                    runner.evidence[row['id']] = copy.deepcopy(row)
                    env.dependencies.update(row.get('dependency_after', row.get('stable_dependencies', {})))
                runner.progress = DeliveryProgress(runner.task, env)
                runner.history = copy.deepcopy(old.get('recent_decisions', []))
                runner.advice = copy.deepcopy(panel.get('advice', {}))
                runner.last_feedback = copy.deepcopy(panel.get('feedback', {}))
                runner.monitor_review = copy.deepcopy(panel.get('semantic_review', {}))
                runner.memory_notices = []
                runner.pending_memory_intervention = copy.deepcopy(panel.get('memory_intervention'))
                runner.checkpoints = {c['id']: dict(c, record=dict(fingerprint=c['fingerprint']))
                                      for c in panel.get('checkpoints', [])}
                runner.counts['model_requests'] = 0
                runner.counts['tool_calls'] = tools
                runner.started_at = time.monotonic(); runner.deadline = runner.started_at+3600
                runner.conversation = conversation
                runner.clients['action'] = Capture([SUBMIT])
                query = runner._memory_query('', list(evidence.values())[-6:])
                candidate_ids = [m['id'] for m in runner.memory.recall(query, env.scope(),
                    env.dependency_state(runner.memory.dependency_targets()))]
                old_ids = event.get('memory_ids', [])
                counters['actor_requests'] += 1
                counters['old_with_memory'] += bool(old_ids)
                counters['old_empty_with_retrievable'] += bool(candidate_ids) and not old_ids
                try:
                    runner._ask('action')
                    new = runner.clients['action'].prompts[-1]
                    new_ids = [m['id'] for m in new['fixed_context']['memories']]
                    counters['new_with_memory'] += bool(new_ids)
                    counters['new_empty_with_retrievable'] += bool(candidate_ids) and not new_ids
                    counters['explicit_reserve_omissions'] += len(new['fixed_context']['memory_budget']['omitted_ids'])
                    call = runner.clients['action'].calls[-1]
                    actual_messages = [dict(role='system', content=call['system_prompt']),
                        *call['history_messages'], dict(role='user', content=call['user_prompt'])]
                    counters['complete_requests_within_original_budget'] += (
                        runner.config.context_chars-1024 >=
                        message_chars(actual_messages))
                    if tools in (100,200):
                        examples.append(dict(after_tools=tools, old_ids=old_ids,
                            new_ids=new_ids, retained=[dict(id=m['id'], conclusion=m['conclusion'])
                            for m in new['fixed_context']['memories']]))
                except Exception as error:
                    counters['replay_errors'] += 1
                    if counters['replay_errors'] <= 3:
                        examples.append(dict(after_tools=tools, error_type=type(error).__name__, detail=str(error)))
    report = dict(source=str(path), mode='offline recorded-state replay, not new solving or reward evidence',
        config=dict(context_chars=48000, memory_reserve_chars=8000), counters=dict(counters), examples=examples)
    return report


if __name__ == '__main__':
    result = replay(ROOT/'evidence/original-foldseek-C1-events.jsonl')
    atomic_json(ROOT/'evidence/replay-result.json', result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
