"""Receive an authorized standby key via SSH stdin; never print it."""
from pathlib import Path
import hashlib,json,os,sys,time
R=Path(__file__).resolve().parent.parent
data=json.loads(sys.stdin.readline(16384));key=data['key'].strip()
assert key.startswith('sk-') and key.isascii() and not any(c.isspace() for c in key)
root=Path.home()/'.config'/'appworld-credentials'
root.mkdir(mode=0o700,parents=True,exist_ok=True);root.chmod(0o700)
target=root/'taotoken-standby.json'
flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL
fd=os.open(target,flags,0o600)
with os.fdopen(fd,'w') as f:json.dump({'key':key,'endpoint':'https://api.taotoken.net/token/v1/messages'},f)
metadata={'created':time.time(),'account_label':'sidebar-account-ending-8991','state':'saved_standby_not_hot_loaded','key_sha256':hashlib.sha256(key.encode()).hexdigest(),'credential_path':str(target),'switch_condition':'primary_provider_quota_exhausted','budget_ledger':str(R/'spending.sqlite'),'campaign_limit_cny':720,'attempt_limit_cny':8,'model':'deepseek-flash','note':'Existing running controller has an in-memory primary key. Resume with standby after quota stop; preserve finished results and cumulative ledger. No automatic hot failover installed.'}
(R/'standby-api.json').write_text(json.dumps(metadata,indent=2))
print(json.dumps({'saved':True,'mode':oct(target.stat().st_mode&0o777),'state':metadata['state']}))
