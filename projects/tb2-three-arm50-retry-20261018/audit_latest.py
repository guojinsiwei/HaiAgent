import json,collections,datetime,sqlite3
from pathlib import Path
from recovery import owned_alive
R=Path(__file__).resolve().parent
P=R.parent/'tb2-three-arm50-20261017'
h=json.loads((R/'health.json').read_text());parent=json.loads((P/'health.json').read_text())
errors=collections.Counter();examples={}
for row in h['rows']:
 t=Path(row.get('result',{}).get('trial','/missing'));r=t/'result.json'
 if not r.exists():continue
 e=json.loads(r.read_text()).get('exception_info') or {}
 if e:
  message=e.get('exception_message','');errors[message]+=1;examples.setdefault(message,str(t))
print(json.dumps(dict(checked_at=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),parent_alive=owned_alive(parent.get('supervisor_identity')),retry_alive=owned_alive(h.get('supervisor_identity')),active=h.get('active'),errors=[dict(message=k,count=v,example=examples[k]) for k,v in errors.items()]),ensure_ascii=False))
for message,t in examples.items():
 print('EXAMPLE',message)
 for name in ('agent/setup/stdout.txt','agent/setup/stderr.txt','agent/setup.log','trial.log','agent/command-0/stdout.txt','agent/command-0/stderr.txt'):
  p=Path(t)/name
  if p.exists():print(name,p.read_text(errors='replace')[-1600:])
with sqlite3.connect('file:'+str(P/'spending.sqlite')+'?mode=ro',uri=True) as db:
 snapshot=json.loads((R/'parent-final.json').read_text())['spending']
 total=db.execute("SELECT coalesce(sum(CASE WHEN state='settled' THEN actual ELSE reserved END),0),count(*) FROM calls").fetchone()
 print('CHARGES',json.dumps(dict(parent_snapshot=snapshot,total_charged_microcny=total[0],calls=total[1])))
