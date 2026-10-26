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
result = LocalExecutor(task, config).execute(payload['command'], time.monotonic() + payload['remaining'])
print(json.dumps(result.payload()))
