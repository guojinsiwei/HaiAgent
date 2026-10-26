"""Real executor smoke run with a scripted policy and an independent public test."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from .protocol import Config, Task
from .runtime import run
from .storage import atomic_json


class ScriptedClient:
    model = "scripted-offline-no-API"

    def __init__(self, decisions):
        self.decisions = iter(decisions)
        self.requests = []

    def complete(self, messages, deadline, recorder):
        self.requests.append(messages)
        return {"content": json.dumps(next(self.decisions)), "complete": True}


def demo(output):
    with tempfile.TemporaryDirectory(prefix="hai-offline-demo-") as temporary:
        root = Path(temporary)
        workspace = root / "workspace"
        workspace.mkdir()
        (workspace / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
        for argv in (["git", "init", "-q"], ["git", "add", "calc.py"],
                     ["git", "-c", "user.name=HAI Demo", "-c", "user.email=demo@invalid", "commit", "-qm", "seed"]):
            subprocess.run(argv, cwd=workspace, capture_output=True, check=True)
        client = ScriptedClient([
            {"action": "run", "argv": [sys.executable, "-c", "from pathlib import Path; print(Path('calc.py').read_text())"]},
            {"action": "run", "argv": [sys.executable, "-c", "from pathlib import Path; Path('calc.py').write_text('def add(a, b):\\n    return a + b\\n'.replace('\\\\n', '\\n'))"]},
            {"action": "run", "argv": [sys.executable, "-c", "from calc import add; assert add(2, 3) == 5; print('targeted assertion passed')"]},
            {"action": "submit", "summary": "Fixed add; targeted assertion executed. Independent evaluation pending."},
        ])
        result = run(Task("offline-add", "Fix add(a, b) to add rather than subtract", workspace),
                     Config(max_turns=8, wall_seconds=60), client, output)
        # This is a DEMO public assertion, not a benchmark result or claimed official success.
        check = subprocess.run([sys.executable, "-c", "from calc import add; assert add(8, 2) == 10; assert add(-1, 3) == 2"],
                               cwd=workspace, capture_output=True, timeout=5)
        atomic_json(Path(output) / "demo-check.json", {"demo_only": True, "exit_code": check.returncode,
                                                      "stdout": check.stdout.decode(), "stderr": check.stderr.decode()})
        return result | {"demo_check_passed": check.returncode == 0,
                         "note": "Scripted offline test; no API calls and no benchmark performance claim."}
