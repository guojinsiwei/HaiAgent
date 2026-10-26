"""Unprivileged task-side command executor; contains no model credentials."""
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

sys.path.insert(0, '/opt/lhtb-agent-tools/src')
sys.path.insert(0, str(Path(__file__).resolve().parent))
from haiagent.executor import LocalExecutor
from process_cleanup import enable_subreaper, cleanup_children

payload = json.load(sys.stdin)
task = SimpleNamespace(workspace=Path('/app'), environment={})
config = SimpleNamespace(command_seconds=900, output_bytes=16000)
command = payload['command']
enable_subreaper()
handle = None
if command.get('capture_execution'):
    from shell_probe import prepare_trace, finish_trace
    command, handle = prepare_trace(command)
try:
    result = LocalExecutor(task, config).execute(command, time.monotonic() + payload['remaining'])
finally:
    cleanup = cleanup_children()
    if payload['command'].get('capture_execution'):
        observation = finish_trace(handle)
cleanup['command_exit_code'] = result.exit_code
cleanup['file_only_violation'] = bool(cleanup['killed'] and not result.timed_out)
if cleanup['file_only_violation']:
    result.exit_code = 126
    cleanup['notice'] = 'Detached command children terminated; file-only tasks do not support background services.'
value = result.payload()
if payload['command'].get('capture_execution'):
    observation['process_cleanup'] = cleanup
    value['execution_observation'] = observation
else:
    value['execution_observation'] = dict(coverage='not_instrumented',complete=False,
                                         process_cleanup=cleanup)
print(json.dumps(value))
