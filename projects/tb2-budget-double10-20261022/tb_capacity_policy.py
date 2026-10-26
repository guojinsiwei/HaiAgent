from pathlib import Path
import collections,json,os,shutil,subprocess
ROOT=Path(__file__).resolve().parent
def external_rows():return []
def choose(rows,active_arms,external):
 busy=collections.Counter(active_arms);out=[]
 waiting={a:any(r['arm']==a and r['state']=='pending' for r in rows) for a in ['hld','recuris']}
 for r in rows:
  if sum(busy.values())>=6:break
  a=r['arm'];other='recuris' if a=='hld' else 'hld';limit=3 if waiting[other] or busy[other] else 6
  if r['state']=='pending' and busy[a]<limit:out.append(r);busy[a]+=1
 return out
def space_ready(task,active):
 if len(active)>=6:return False
 tasks={x['name']:x for x in json.loads((ROOT/'tasks.json').read_text())['tasks']}
 image=tasks[task]['environment']['docker_image']
 cold=subprocess.run(['docker','image','inspect',image],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=20).returncode!=0
 reserve=(24+10*(len(active)+1)+(20 if cold else 0))*2**30
 mem=dict(line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())
 return shutil.disk_usage('/var/lib/docker').free>=reserve and shutil.disk_usage(ROOT).free>=8*2**30 and int(mem['MemAvailable'].split()[0])*1024>=24*2**30 and os.getloadavg()[0]<(os.cpu_count() or 1)*.8
