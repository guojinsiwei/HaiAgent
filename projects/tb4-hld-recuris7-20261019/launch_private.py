"""Use the already-authorized server-side credential, without printing it."""
from pathlib import Path
import json,subprocess
R=Path(__file__).resolve().parent
assert json.loads((R/'ready.json').read_text())['passed']
p=Path.home()/'.config/appworld-credentials/taotoken-standby.json'
bundle=json.loads(p.read_text());key=bundle['key'];assert isinstance(key,str) and key.strip()
result=subprocess.run([str(R/'venv/bin/python'),str(R/'campaign.py'),'--launch'],input=json.dumps({'key':key})+'\n',text=True,capture_output=True,cwd=R)
output=(result.stdout+result.stderr).replace(key,'[REDACTED]');key='';bundle.clear()
print(output);raise SystemExit(result.returncode)
