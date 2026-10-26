"""Raw controller remains outside sandbox; only tool commands enter it."""
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / 'runtime'))
from haiagent.executor import LocalExecutor, Result
from haiagent.model import APIClient, ModelError
from haiagent.storage import read_trace
from haiagent.protocol import Config, Task
from haiagent.runtime import run
from haiagent.demo import ScriptedClient

PYTHON = '/mnt/lizh639/envs/swe-eval/bin/python'

class SandboxExecutor(LocalExecutor):
    def __init__(self, task, config, root):
        super().__init__(task, config)
        self.image_root = root

    def execute(self, command, deadline):
        cwd = posixpath.normpath(posixpath.join('/app', command.get('cwd', '.')))
        # Accept the controller's workspace spelling too, but never expose its parents.
        host = str(self.task.workspace)
        if cwd == host or cwd.startswith(host + '/'):
            cwd = '/app' + cwd[len(host):]
        if cwd != '/app' and not cwd.startswith('/app/'):
            return Result(126, stderr='cwd must be inside /app', blocked=True)
        argv = ['setpriv', '--reuid', '65534', '--regid', '65534', '--clear-groups',
                'unshare', '--user', '--map-root-user', '--pid', '--net', '--fork', '--kill-child=KILL',
                PYTHON, str(HERE / 'chroot_entry.py'), str(self.image_root),
                json.dumps({'cwd': cwd, 'argv': command['argv']})]
        return super().execute(dict(command, argv=argv, cwd='.'), deadline)

class AuditedClient(APIClient):
    recoveries = 0

    def complete(self, messages, deadline, recorder):
        # Only an environment path translation, not an additional reasoning policy.
        messages = json.loads(json.dumps(messages))
        payload = json.loads(messages[1]['content'])
        payload['workspace'] = '/app'
        messages[1]['content'] = json.dumps(payload, ensure_ascii=False)
        recorder.emit('model_request_full', messages=messages)
        for retry in range(4):
            try:
                result = super().complete(messages, deadline, recorder)
                break
            except ModelError as error:
                reason = str(error)
                transient = reason in {'provider_URLError', 'provider_TimeoutError',
                    'provider_absolute_request_timeout', 'provider_ConnectionResetError',
                    'provider_408', 'provider_429'} or reason in {f'provider_{n}' for n in range(500,600)}
                delay = [10,30,60][min(retry,2)]
                if not transient or retry == 3 or self.recoveries >= 6 or time.monotonic()+delay >= deadline:
                    raise
                self.recoveries += 1
                recorder.emit('transport_recovery', reason=reason, delay_seconds=delay,
                              task_recoveries=self.recoveries, request_recovery=retry+1)
                time.sleep(delay)
        recorder.emit('model_response_full', response=result)
        return result

class Replay:
    def __init__(self, path):
        self.events = read_trace(path)
        self.responses = [e for e in self.events if e['event'] == 'model_response_full']
        self.starts = [e for e in self.events if e['event'] == 'tool_start']
        self.ends = [e for e in self.events if e['event'] == 'tool_end']
        self.result = next(e['result'] for e in reversed(self.events) if e['event']=='run_end')
        assert self.result['stop_reason'] == 'api_error' and not self.result['submitted']
        assert len(self.responses) == len(self.starts) == len(self.ends) == 29
        assert not any(e['event']=='format_error' for e in self.events)
        self.expected = [e['messages'] for e in self.events if e['event']=='model_request_full'][-1]
        self.model_index = self.tool_index = 0
        self.checked = False
        self.recorder = None

    @staticmethod
    def comparable(messages):
        messages = json.loads(json.dumps(messages))
        value = json.loads(messages[1]['content'])
        value.pop('budgets_remaining', None)
        value['workspace'] = '/app'
        messages[1]['content'] = value
        return messages

class ResumeClient(AuditedClient):
    def complete(self, messages, deadline, recorder):
        replay = self.replay
        replay.recorder = recorder
        if replay.model_index < len(replay.responses):
            item = replay.responses[replay.model_index]
            replay.model_index += 1
            recorder.emit('replayed_response', original_sequence=item['sequence'], api_call=False)
            return item['response']
        if not replay.checked:
            assert replay.tool_index == 29
            assert replay.comparable(messages) == replay.comparable(replay.expected), 'Resume context mismatch; no API call'
            replay.checked = True
            recorder.emit('resume_context_verified', prior_turns=29, prior_tools=29,
                          prior_wall_seconds=replay.result['wall_seconds'])
        if getattr(self, 'offline_resume_test', False):
            return {'complete': True, 'content': json.dumps({'action':'submit','summary':'Offline resume validation only'})}
        return super().complete(messages, deadline, recorder)

class ResumeExecutor(SandboxExecutor):
    def execute(self, command, deadline):
        replay = self.replay
        if replay.tool_index < len(replay.ends):
            i = replay.tool_index
            assert command == replay.starts[i]['command'], 'Replay action mismatch'
            replay.tool_index += 1
            replay.recorder.emit('replayed_tool', original_sequence=replay.ends[i]['sequence'], executed=False)
            return Result(**replay.ends[i]['result'])
        return super().execute(command, deadline)

def run_one(task_id, key, *, fixture=False, resume_test=False):
    manifest = json.loads((HERE / 'protocol.json').read_text())
    root = HERE / 'roots' / task_id
    instruction = (root / 'app/INSTRUCTION.md').read_text()
    replay = Replay(HERE/'prior-scheme-events.jsonl') if task_id=='cs61_fa24_scheme' and not fixture else None
    budgets = dict(manifest['budgets'])
    if replay:
        budgets['wall_seconds'] -= replay.result['wall_seconds']
    config = Config(method='raw', response_protocol='tool_call', **budgets)
    task = Task(task_id, 'Read INSTRUCTION.md and complete the specified project.\n' + instruction[:18000],
                root / 'app', delivery='terminal', environment_revision=manifest['image_id'],
                constraints=('Only public project files are available; hidden tests are applied after submission.',
                 'This is a single-final-grading diagnostic. Decide yourself when to submit; no hidden-test retry loop.',
                 'Network is disabled for task commands. Python and the task dependencies are preinstalled.',
                 'System files are protected; keep project changes in /app and temporary files in /tmp. Each command has a fresh process namespace; background services do not persist.'))
    if fixture:
        client = ScriptedClient([
            {'action': 'run', 'argv': ['python3', '-c', 'from pathlib import Path; assert Path("INSTRUCTION.md").is_file(); print("fixture-ok")']},
            {'action': 'submit', 'summary': 'Zero-call infrastructure fixture, not a task solution'}])
    else:
        cls = ResumeClient if replay else AuditedClient
        client = cls(manifest['endpoint'], manifest['model'], key, config)
    executor = ResumeExecutor(task, config, root) if replay else SandboxExecutor(task, config, root)
    if replay:
        client.replay = executor.replay = replay
        client.offline_resume_test = resume_test
    return run(task, config, client, HERE / ('resume-fixture' if resume_test else 'fixtures' if fixture else 'runs') / task_id,
               executor=executor, secrets=(key,) if key else ())
