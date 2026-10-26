"""Bounded admission for both arms, with no interruption of active trials."""
from pathlib import Path
import collections,json,os,shutil,subprocess
ROOT=Path(__file__).resolve().parent
def external_rows():return []
def choose(rows,active_arms,external):
 busy=collections.Counter(active_arms);result=[]
 waiting={a:any(r['arm']==a and r['state']=='pending' for r in rows) for a in ['hld','recuris']}
 for row in rows:
  if sum(busy.values())>=8:break
  arm=row['arm'];other='recuris' if arm=='hld' else 'hld'
  limit=4 if waiting[other] or busy[other] else 8
  if row['state']=='pending' and busy[arm]<limit:result.append(row);busy[arm]+=1
 return result
def space_ready(task,active):
 if len(active)>=8:return False
 tasks={x['name']:x for x in json.loads((ROOT/'tasks.json').read_text())['tasks']}
 image=tasks[task]['environment']['docker_image']
 cold=subprocess.run(['docker','image','inspect',image],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=20).returncode!=0
 assert all(x['environment']['storage']=='10G' for x in tasks.values())
 reserve=(24+10*(len(active)+1)+(20 if cold else 0))*2**30
 mem=dict(line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())
 return (shutil.disk_usage('/var/lib/docker').free>=reserve and shutil.disk_usage(ROOT).free>=8*2**30
         and int(mem['MemAvailable'].split()[0])*1024>=24*2**30 and os.getloadavg()[0]<(os.cpu_count() or 1)*.8)
