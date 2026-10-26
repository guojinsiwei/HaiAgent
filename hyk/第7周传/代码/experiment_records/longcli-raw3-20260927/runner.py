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
from haiagent.model import APIClient
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
    def complete(self, messages, deadline, recorder):
        # Only an environment path translation, not an additional reasoning policy.
        messages = json.loads(json.dumps(messages))
        payload = json.loads(messages[1]['content'])
        payload['workspace'] = '/app'
        messages[1]['content'] = json.dumps(payload, ensure_ascii=False)
        recorder.emit('model_request_full', messages=messages)
        result = super().complete(messages, deadline, recorder)
        recorder.emit('model_response_full', response=result)
        return result

def run_one(task_id, key, *, fixture=False):
    manifest = json.loads((HERE / 'protocol.json').read_text())
    root = HERE / 'roots' / task_id
    instruction = (root / 'app/INSTRUCTION.md').read_text()
    config = Config(method='raw', response_protocol='tool_call', **manifest['budgets'])
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
        client = AuditedClient(manifest['endpoint'], manifest['model'], key, config)
    return run(task, config, client, HERE / ('fixtures' if fixture else 'runs') / task_id,
               executor=SandboxExecutor(task, config, root), secrets=(key,) if key else ())
