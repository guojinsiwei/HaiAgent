"""Unprivileged task-side command executor; contains no model credentials."""
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

sys.path.insert(0, '/opt/lhtb-agent-tools/src')
from haiagent.executor import LocalExecutor

payload = json.load(sys.stdin)
task = SimpleNamespace(workspace=Path('/app'), environment={})
config = SimpleNamespace(command_seconds=900, output_bytes=16000)
command = payload['command']
handle = None
if command.get('capture_execution'):
    from shell_probe import prepare_trace, finish_trace
    command, handle = prepare_trace(command)
try:
    result = LocalExecutor(task, config).execute(command, time.monotonic() + payload['remaining'])
finally:
    if payload['command'].get('capture_execution'):
        observation = finish_trace(handle)
value = result.payload()
if payload['command'].get('capture_execution'):
    value['execution_observation'] = observation
print(json.dumps(value))
