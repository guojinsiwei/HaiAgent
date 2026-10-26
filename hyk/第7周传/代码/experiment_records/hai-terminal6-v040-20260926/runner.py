"""Runs inside the task container; output is persisted through Harbor's agent log mount."""
import json
import os
from pathlib import Path
import sys

from haiagent.cli import run_exit_code
from haiagent.demo import ScriptedClient
from haiagent.model import APIClient
from haiagent.protocol import Config, Task
from haiagent.runtime import run
from haiagent.storage import atomic_json


def main():
    payload = json.loads(Path('/installed-agent/input.json').read_text())
    task = Task(payload['task_id'], payload['instruction'], Path('/app'), delivery='terminal',
                constraints=('Use only the public task instruction and live task environment. Do not inspect hidden verifier tests, /tests, /solution, or controller credentials.',))
    config = Config(method=payload['method'], wall_seconds=payload['wall_seconds'],
                    response_protocol='tool_call', max_consecutive_format_errors=3, max_format_errors=8)
    key = os.environ.get('DEEPSEEK_API_KEY', '')
    if payload['fixture']:
        # Infrastructure fixture only; no attempt to solve the benchmark, no model/API.
        actions = [
            {'action': 'run', 'argv': [sys.executable, '-c', 'print("offline-linux-agent-feedback")']},
            {'action': 'submit', 'summary': 'Infrastructure fixture only; no benchmark solution attempted'},
        ]
        client = ScriptedClient(actions)
    else:
        client = APIClient('https://api.deepseek.com', payload['model'], key, config)
    result = run(task, config, client, '/logs/agent/haia-run', secrets=(key,) if key else ())
    atomic_json('/logs/agent/transport-status.json', {
        'method': payload['method'], 'task_id': payload['task_id'], 'fixture': payload['fixture'],
        'submitted': result['submitted'], 'stop_reason': result['stop_reason'],
        'interaction_rounds': result['interaction_rounds'], 'tool_calls': result['tool_calls'],
        'official_success': None, 'exit_code': run_exit_code(result)})
    return run_exit_code(result)


if __name__ == '__main__':
    raise SystemExit(main())
