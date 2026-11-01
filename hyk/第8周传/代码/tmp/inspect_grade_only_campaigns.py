"""Allowlisted grade-only campaigns omitted by jobs/health collectors."""
import json
from pathlib import Path
roots=[
 '/var/tmp/lizh639-longcli-dsh20-byte-context-repair-20261006',
 '/var/tmp/lizh639-longcli-planner-v3-10-20261004',
 '/var/tmp/lizh639-longcli-dh-raw-full20-20261004',
 '/var/tmp/lizh639-longcli-reflexion20-college-20261006',
 '/var/tmp/lizh639-longcli-reflexion-recovery-20261006',
 '/mnt/sdb/home/lizh639/longcli-resume-five-20261007/dh-resume-20261007',
 '/mnt/sdb/home/lizh639/longcli-dh-large20-20261007']
for name in roots:
 root=Path(name);methods={}
 for p in (root/'grades').glob('*/result.json'):
  r=json.loads(p.read_text())
  if r.get('grading_state')!='complete':continue
  m=p.parent.name.split('--')[0];s=r.get('f2p',{}).get('step_score')
  methods.setdefault(m,[]).append({'task':p.parent.name.split('--')[-1],
      'score':s,'official_success':r.get('official_success')})
 print(json.dumps({'root':name,'exists':root.exists(),'methods':{
   m:{'graded':len(rows),'mean':sum(r['score'] for r in rows)/len(rows),
      'full_passes':sum(r['official_success'] is True for r in rows),
      'tasks':[r['task'] for r in rows]} for m,rows in methods.items()}}))
print(json.dumps({'other_matching_roots':[str(p) for parent in ('/var/tmp','/mnt/sdb/home/lizh639')
 for p in Path(parent).iterdir() if p.is_dir() and 'longcli' in p.name.lower()
 and any(word in p.name.lower() for word in ('graph','dual','solver','multi','paired'))]}))
