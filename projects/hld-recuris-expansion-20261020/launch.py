"""Use the previously authorized private server credential without printing it."""
from pathlib import Path
import json,subprocess,sys,time
R=Path(__file__).resolve().parent;H=R.parent
def read(p):return json.loads(p.read_text())
def main():
 assert read(R/'validation.json')['passed']
 (R/'launch-once.marker').open('x').write(str(time.time()))
 cred=read(Path.home()/'.config/appworld-credentials/taotoken-standby.json')
 key=cred.get('key') or cred.get('api_key') or cred.get('apiKey')
 assert isinstance(key,str) and key.strip(),'Authorized private credential missing'
 results=[]
 for name,entry,python in [('appworld-hld-recuris70-20261020','app_campaign.py','python3'),('tb2-hld-recuris50-20261020','campaign.py',str(H/'tb2-hld-recuris50-20261020/venv/bin/python'))]:
  p=subprocess.run([python,str(H/name/entry),'--launch'],input=json.dumps(dict(key=key)),capture_output=True,text=True,timeout=180)
  safe=(p.stdout+p.stderr).replace(key,'[REDACTED]')
  (R/(name+'-launch.log')).write_text(safe)
  assert p.returncode==0,safe[-1500:]
  results.append(dict(campaign=name,result=safe.strip()))
 key=''
 (R/'launch-receipt.json').write_text(json.dumps(dict(time=time.time(),results=results),indent=2))
 print(json.dumps(results,indent=2))
if __name__=='__main__':main()
