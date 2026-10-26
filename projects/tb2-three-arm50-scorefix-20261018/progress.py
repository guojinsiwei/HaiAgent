import datetime,json,shutil,sqlite3
from pathlib import Path
R=Path(__file__).resolve().parent
print('TIME',datetime.datetime.now().isoformat())
print('DISK_GIB',round(shutil.disk_usage('/var/lib/docker').free/1024**3,1))
for p in sorted((R/'dependency-cache').glob('*/warm.log')):
 ready=(p.parent/'ready.json').exists();print('CACHE',p.parent.name,ready,p.read_text(errors='replace')[-300:].replace('\n',' | '))
for p in R.glob('accept-*.json'):
 r=json.loads(p.read_text());print('ACCEPT',r['task'],r.get('engineering_clean'),r.get('exception_type'),r.get('trial'))
for p in (R/'preflight').glob('*/*/lifecycle.json'):
 r=json.loads(p.read_text())
 if r['stage']!='cleanup_succeeded':
  print('LIVE',p.parent.name,r['stage'])
  for filename in ('offline-resolution.log','test-stdout.txt'):
   log=p.parent/'verifier'/filename
   if log.exists():print(filename,log.read_text(errors='replace')[-400:].replace('\n',' | '))
with sqlite3.connect('file:'+str(R.parent/'tb2-three-arm50-20261017/spending.sqlite')+'?mode=ro',uri=True) as db:
 print('LEDGER',db.execute("select count(*),sum(case when state='settled' then actual else reserved end) from calls").fetchone())
