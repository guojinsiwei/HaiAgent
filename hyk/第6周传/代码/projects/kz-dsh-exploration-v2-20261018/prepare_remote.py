"""Keyless LongCLI environment and isolated source acceptance. Never invokes an LLM."""
import hashlib,json,os,shutil,subprocess,sys,tarfile
from pathlib import Path
R=Path(__file__).resolve().parent
OLD=Path('/var/tmp/lizh639-longcli-dsh20-20261005')
ASSETS=Path('/var/tmp/lizh639-longcli-v6-raw-paired10-20261001')
STARTERS=Path('/var/tmp/lizh639-longcli-dh-raw-full20-20261004')
TB=Path('/mnt/sdb/home/lizh639/tb2-three-arm50-20261017')
TASKS=['61810_util','cs61_fa24_ants','cs61_fa24_scheme','61810_mmap','ap1400_2_hw26','cmu15_445_p1']
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def save(name,v):
 p=R/name;t=p.with_suffix(p.suffix+'.tmp');t.write_text(json.dumps(v,indent=2));t.replace(p)
def command(args,log,seconds=600):
 with (R/log).open('a') as f:
  p=subprocess.run(args,stdout=f,stderr=subprocess.STDOUT,timeout=seconds)
 if p.returncode:raise RuntimeError('Operation failed; see '+log)
def main():
 assert R.name=='kz-dsh-exploration-v2-20261018'
 assert not (R/'launch-once.marker').exists(),'Never alter launched experiment'
 assert shutil.disk_usage('/var/lib/docker').free>60*2**30,'Keep current campaigns safe'
 for name in ('common.py','college_grader.py','input-manifest.json'):
  if not (R/name).exists():shutil.copy2(OLD/name,R/name)
 if not (R/'upstream').exists():(R/'upstream').symlink_to(OLD/'upstream',target_is_directory=True)
 for arm in ('baseline','candidate'):
  modules=R/arm/'node_modules'
  if not modules.exists():modules.symlink_to(TB/'runtime/kz/node_modules',target_is_directory=True)
 node=TB/'runtime/node/bin/node'
 # Run the affected suites on Linux with the exact official DSH runtime packages.
 tests=['policy.test.mjs','exploration-trigger.test.mjs','exploration-learning.test.mjs','strategy-execution-repair4.test.mjs','full.test.mjs','recovery-clock-repair5.test.mjs','recovery-integration-repair5.test.mjs','subgoal-integration-repair5.test.mjs','transport-recovery.test.mjs']
 for arm in ('baseline','candidate'):
  selected=tests+(['exploration-v2.test.mjs'] if arm=='candidate' else [])
  command([str(node),'--test','--test-concurrency=2',*[str(R/arm/'tests'/x) for x in selected]],arm+'-linux-tests.log')
 command([str(node),str(R/'compare-offline.mjs')],'offline-comparison.log')
 protocol=json.loads((OLD/'protocol.json').read_text());rows=[next(t for t in protocol['tasks'] if t['task']==n) for n in TASKS]
 restored={}
 for family,base in protocol['base_images'].items():
  archive=ASSETS/base['archive'];assert sha(archive)==base['sha256'],'Base archive differs'
  tag='kz-exploration-v2-base:'+family
  inspect=subprocess.run(['docker','image','inspect',tag,'--format','{{.Id}}'],capture_output=True,text=True)
  if inspect.returncode:
   command(['docker','import','--change','LABEL experiment='+R.name,str(archive),tag],'restore-'+family+'.log')
  restored[family]=dict(tag=tag,archive=str(archive),archive_sha256=base['sha256'],image_id=subprocess.check_output(['docker','image','inspect',tag,'--format','{{.Id}}'],text=True).strip())
 from common import import_tree
 for row in rows:
  starter=STARTERS/('starter-'+row['task']+'.tar.gz');assert starter.exists()
  row['historical_image_id']=row['image_id'];row['starter_path']=str(starter);row['starter_sha256']=sha(starter)
  context=R/'image-contexts'/row['task']
  if not context.exists():import_tree(starter,context)
  (context/'Dockerfile').write_text('FROM '+restored[row['family']]['tag']+'\nWORKDIR /app\nCOPY . /app/\n')
  row['image']='kz-exploration-v2-task:'+row['task']
  inspect=subprocess.run(['docker','image','inspect',row['image'],'--format','{{.Id}}'],capture_output=True,text=True)
  if inspect.returncode:command(['docker','build','--network','none','--label','experiment='+R.name,'-t',row['image'],str(context)],'build-'+row['task']+'.log')
  row['image_id']=subprocess.check_output(['docker','image','inspect',row['image'],'--format','{{.Id}}'],text=True).strip()
 protocol.update(experiment=R.name,tasks=rows,methods=['baseline','candidate'],total_trials=12,workers=2,
  model='deepseek-flash',endpoint='https://api.taotoken.net/token/v1/messages',
  selection='six diagnostic pilot tasks selected before candidate model runs; not a random benchmark estimate',
  budget=dict(authorized_total_cny=96,planned_maximum_cny=48,per_trial_cny=4,requests=120,tools=180,seconds=2700),
  ablation_only_difference='KZDSH exploration trigger, measurement, follow-up and bounded episode policy; same Critic and provider',
  original_task_inputs_identical=True,cross_task_memory=False,official_feedback_to_solver=False,automatic_failed_task_retry=False,
  restored_bases=restored,prior_results_carried=0)
 save('protocol.json',protocol)
 for arm in ('baseline','candidate'):
  runtime=R/'runtime'/arm
  if runtime.exists():continue
  runtime.mkdir(parents=True)
  # Runtime dependencies stay shared read-only; source and deployment configuration are copied.
  for p in (TB/'runtime/kz').iterdir():
   if p.name in ('src','tests','scripts','config','node_modules','.runtime'):continue
   if p.is_file():shutil.copy2(p,runtime/p.name)
  for part in ('src','scripts'):shutil.copytree(R/arm/part,runtime/part)
  shutil.copytree(TB/'runtime/kz/config',runtime/'config')
  # The controller bind-mounts existing dependencies here, read-only.
  (runtime/'node_modules').mkdir()
  (runtime/'.runtime').mkdir()
  for p in (TB/'runtime/kz/.runtime').glob('*.yml'):shutil.copy2(p,runtime/'.runtime'/p.name)
  # Both arms retain identical route/limits and use the original LongCLI instruction.
  patch=runtime/'.runtime/kz.patch.yml';text=patch.read_text().replace('BENCHMARK_INSTRUCTION.md','INSTRUCTION.md')
  patch.write_text(text)
  shutil.copy2(R/'boot-guard.mjs',runtime/'boot-guard.mjs')
 (R/'empty-tests').mkdir(exist_ok=True)
 save('prepared.json',dict(paid_calls=0,tasks=TASKS,images_restored=True,affected_linux_tests_passed=True))
 print('KEYLESS PREPARED',flush=True)
if __name__=='__main__':main()
