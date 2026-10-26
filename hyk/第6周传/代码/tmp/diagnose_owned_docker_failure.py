"""Owned-container Docker events and last action metadata, never environments."""
import json,subprocess,time
from pathlib import Path
ROOT=Path('/var/tmp/longcli-dh-tools-context-repair2-20261008')
d=ROOT/'jobs/dh_tools--cmu15_445_p0'
info=json.loads((d/'container.json').read_text());h=json.loads((d/'health.json').read_text())
last=None
for line in (d/'trace/events.jsonl').open():
    e=json.loads(line)
    if e.get('event')=='tool_attempt':last=e
command=(last or {}).get('command',{})
print(json.dumps({'last_tool_attempt':{'sequence':(last or {}).get('sequence'),
    'command':{k:v for k,v in command.items() if k in ('argv','cwd','purpose')},
    'time':(last or {}).get('time')}}))
for line in (d/'trace/events.jsonl').open():
    e=json.loads(line)
    if e.get('event')=='infrastructure_error':print(json.dumps(e))
print(json.dumps({'workspace_top_names':sorted(p.name for p in (d/'workspace').iterdir())}))
p=subprocess.run(['docker','events','--since',str(int(h['started'])),'--until',str(int(time.time())),
    '--filter','type=container','--filter','container='+info['name'],
    '--filter','label=experiment='+ROOT.name,'--format','{{json .}}'],capture_output=True,text=True,timeout=15)
events=[]
for line in p.stdout.splitlines():
    x=json.loads(line);attrs=x.get('Actor',{}).get('Attributes',{})
    events.append({'action':x.get('Action','').split(':',1)[0],'time':x.get('time'),'exitCode':attrs.get('exitCode')})
print(json.dumps({'owned_container_events':events,'events_returncode':p.returncode}))
print(json.dumps({'owned_container_receipt':info,'quiescence':json.loads((d/'quiescence.json').read_text())
    if (d/'quiescence.json').exists() else None}))
