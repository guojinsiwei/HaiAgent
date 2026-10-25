"""Read-only historical log audit; no model calls and no remote writes."""
import collections, hashlib, json
from pathlib import Path

original=['cs61_fa24_hog','cs61_fa24_scheme','cs61_fa24_ants','cmu15_445_p1','ap1400_2_hw35','61810_fs','61810_pgtbl']
supplement=['cs61_fa24_cats','61810_net','cs61_fa24_hw08','cmu15_445_p0','61810_cow','61810_syscall','61810_lock','61810_mmap','cmu15_445_p2','61810_thread','61810_traps','61810_util','ap1400_2_hw26']
rows=[]
for cohort,tasks,root in [('original7',original,'/var/tmp/longcli-dh-routing3x7-20261008'),('supplement13',supplement,'/mnt/sdb/home/lizh639/longcli-dh-1342-complete20-20261009')]:
 for task in tasks:
  job=Path(root)/'jobs'/('1342--'+task)
  summary=job/'summary.json'
  counts=collections.Counter(); selected=[]; errors=0; config={}
  with (job/'trace/events.jsonl').open() as f:
   for line,s in enumerate(f,1):
    if not s.strip():continue
    try:e=json.loads(s)
    except ValueError:errors+=1;continue
    name=e.get('event');counts[name]+=1
    if 'config' in e and not config:config=e['config']
    if name and ('contrastive' in name or name in ['action_loop_block','recovery_rejection','advisor_trigger']):
     selected.append({'line':line,**{k:v for k,v in e.items() if k not in ['previous','sha256']}})
  rows.append({'cohort':cohort,'task':task,'job':str(job),'summary_sha256':hashlib.sha256(summary.read_bytes()).hexdigest(),'summary':json.loads(summary.read_text()),'config':config,'counts':dict(counts),'parse_errors':errors,'selected':selected})
print(json.dumps({'native20':rows},ensure_ascii=False))
