"""Use the already authorized saved credential without exposing it."""
from pathlib import Path
import json,subprocess
R=Path(__file__).resolve().parent
def main():
 assert json.loads((R/'validation.json').read_text())['passed']
 assert not (R/'launch-once.marker').exists()
 secret=json.loads((Path.home()/'.config/appworld-credentials/taotoken-standby.json').read_text())
 key=secret.get('key') or secret.get('api_key') or secret.get('apiKey')
 assert isinstance(key,str) and key.strip(),'Authorized credential missing'
 p=subprocess.run([str(R/'venv/bin/python'),str(R/'campaign.py'),'--launch'],input=json.dumps(dict(key=key)),text=True,capture_output=True,timeout=180)
 safe=(p.stdout+p.stderr).replace(key,'[REDACTED]')
 (R/'launch-receipt.txt').write_text(safe)
 print(safe);assert p.returncode==0,'Launch failed; inspect existing process before retry'
if __name__=='__main__':main()
