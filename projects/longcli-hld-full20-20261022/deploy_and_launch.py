"""One-shot local experiment controller, no GPT/Codex scheduled task."""
from pathlib import Path
import json,subprocess,time
R=Path(__file__).resolve().parent
deadline=time.monotonic()+1800
while not (R/'prepared.json').exists():
 if time.monotonic()>deadline:raise RuntimeError('Preparation did not finish; no paid run launched')
 time.sleep(10)
subprocess.run(['python3',str(R/'preflight.py')],cwd=R,check=True)
assert json.loads((R/'ready.json').read_text())['passed']
subprocess.run(['python3',str(R/'runner.py'),'--launch'],cwd=R,check=True)
