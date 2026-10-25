"""Start the public-state relay only; no model API calls or email."""
import json,os,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
options={'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}
with (ROOT/'relay-out.log').open('ab') as out,(ROOT/'relay-error.log').open('ab') as err:
 p=subprocess.Popen([sys.executable,'-B',str(ROOT/'fleet_local.py'),'--bridge'],
     stdin=subprocess.DEVNULL,stdout=out,stderr=err,**options)
(ROOT/'relay-launch.json').write_text(json.dumps({'pid':p.pid,'time':time.time(),'model_calls':0}))
print(json.dumps({'relay_pid':p.pid,'model_calls':0,'mail_enabled':False}))
