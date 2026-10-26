"""Restore immutable benchmark dependencies; no provider calls."""
from pathlib import Path
import json,shutil,subprocess,time
ROOT=Path(__file__).resolve().parent
OLD=Path('/var/tmp/lizh639-longcli-dh-raw-full20-20261004')
BASE=Path('/var/tmp/lizh639-longcli-v6-raw-paired10-20261001')
HLD=Path('/mnt/sdb/home/lizh639/tb2-hld-mechanism-ab10-20261022')

def run(*args):return subprocess.check_output(list(map(str,args)),text=True).strip()

def main():
 for name in ['common.py','college_grader.py','input-manifest.json']:
  if not (ROOT/name).exists():shutil.copy2(OLD/name,ROOT/name)
 from common import sha,save
 if not (ROOT/'upstream').exists():shutil.copytree(OLD/'upstream',ROOT/'upstream',symlinks=True)
 for name in ['spending.py','container-run.mjs']:
  if not (ROOT/name).exists():shutil.copy2(HLD/name,ROOT/name)
 if not (ROOT/'runtime').exists():
  (ROOT/'runtime').mkdir()
  for name in ['kz','node']:shutil.copytree(HLD/'bundle'/name,ROOT/'runtime'/name,symlinks=True)
 shutil.copy2(ROOT/'container-run.mjs',ROOT/'runtime/kz/container-run.mjs')
 (ROOT/'empty-tests').mkdir(exist_ok=True)
 manifest=json.loads((ROOT/'input-manifest.json').read_text())
 for name,digest in manifest['files'].items():assert sha(ROOT/name)==digest,name
 old=json.loads((OLD/'protocol.json').read_text())
 restored={}
 for family,desc in old['base_images'].items():
  archive=BASE/desc['archive'];assert sha(archive)==desc['sha256']
  tag=ROOT.name+'/'+family+':2015f37'
  probe=subprocess.run(['docker','image','inspect',tag],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  if probe.returncode:
   run('docker','import','--change','ENV PATH=/root/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin','--change','WORKDIR /app','--change','CMD ["bash"]',archive,tag)
  restored[family]=dict(tag=tag,archive_sha256=sha(archive),id=run('docker','image','inspect',tag,'--format','{{.Id}}'))
  print('restored',family,flush=True)
 rows=[]
 for original in old['tasks']:
  row=dict(original);task=row['task'];tag=ROOT.name+'/task-'+task+':2015f37'
  source=ROOT/'upstream/tasks_long_cli'/task
  text=(source/'Dockerfile').read_text().replace('tb/'+row['family']+':v0',restored[row['family']]['tag'])
  definition=ROOT/('Dockerfile.'+task);definition.write_text(text)
  with (ROOT/('build-'+task+'.log')).open('w') as log:
   subprocess.run(['docker','build','--network','none','--label','experiment='+ROOT.name,'-f',str(definition),'-t',tag,str(source)],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=600)
  starter=ROOT/('starter-'+task+'.tar.gz')
  if not starter.exists():shutil.copy2(OLD/starter.name,starter)
  row.update(image=tag,image_id=run('docker','image','inspect',tag,'--format','{{.Id}}'),historical_image_id=original['image_id'],starter_path=str(starter),starter_sha256=sha(starter))
  rows.append(row);print('prepared',task,flush=True)
 assert len(rows)==20 and len({r['task'] for r in rows})==20
 protocol=dict(experiment=ROOT.name,commit=old['commit'],tasks=rows,methods=['hld'],total_trials=20,model='deepseek-flash',version='HLD v8',concurrency=6,cpu_per_task=2,memory_gib_per_task=8,wall_seconds=7200,requests_per_task=400,tools_per_task=600,thinking=False,temperature=0,task_budget_cny=8,campaign_budget_cny=160,all_auxiliary_calls_included=True,automatic_paid_retries=False,official_feedback_to_solver=False,cross_task_memory=False,scoring='official f2p is_pass AND p2p is_pass; separate fresh grader',restored_bases=restored)
 save(ROOT/'protocol.json',protocol)
 profile=json.loads((HLD/'budget-profile.json').read_text());profile['jobs']=['hld--'+r['task'] for r in rows];save(ROOT/'budget-profile.json',profile)
 lock={p.relative_to(ROOT).as_posix():sha(p) for p in (ROOT/'runtime/kz').rglob('*') if p.is_file() and 'node_modules' not in p.parts}
 save(ROOT/'algorithm-source-lock.json',dict(source=str(HLD/'bundle/kz'),files=lock,version='HLD v8',changes='deployment adapter only'))
 save(ROOT/'prepared.json',dict(prepared=True,tasks=20,paid_calls=0,created=time.time()))
 print('PREPARATION COMPLETE',flush=True)

if __name__=='__main__':main()
