"""Validate grading with fresh starter artifacts before any paid model request."""
import json,shutil,subprocess,sys,time,os,secrets
from pathlib import Path
R=Path(__file__).resolve().parent
TB=R.parent/'tb2-three-arm50-20261017'
def main():
 from common import sha,save
 from runner import docker
 from college_grader import grade
 import college_grader
 from grading_environment import install
 install(college_grader,R.name)
 assert (R/'prepared.json').exists() and not (R/'launch-once.marker').exists()
 protocol=json.loads((R/'protocol.json').read_text())
 # Correct host deployment paths after staging. Both arms get identical bounded overlays.
 for arm in protocol['methods']:
  runtime=R/'runtime'/arm;modules=runtime/'node_modules'
  if modules.is_symlink():
   assert modules.resolve()==(TB/'runtime/kz/node_modules').resolve();modules.unlink();modules.mkdir()
  shutil.copytree(TB/'runtime/kz/config',runtime/'config',dirs_exist_ok=True)
  assert 'maxTokens: 16384' in (runtime/'config/common.patch.yml').read_text()
  assert 'maxTokens: 32768' not in (runtime/'config/common.patch.yml').read_text()
  shutil.copy2(R/'boot-guard.mjs',runtime/'boot-guard.mjs')
 # Exercise the actual mounted entrypoint, all guards and lease denial offline.
 subprocess.run([sys.executable,str(R/'entry_acceptance.py')],cwd=R,check=True)
 # Validate deployment YAML, imports, actual native shell, and result propagation
 # inside both task toolchains. No network and no real credential are available.
 from common import import_tree
 runtime_checks=[]
 for family in ['make-pytest','c-env']:
  task=next(r for r in protocol['tasks'] if r['family']==family)
  for arm in protocol['methods']:
   d=R/'runtime-acceptance'/(arm+'-'+family);report=d/'audit/checks.json'
   if report.exists() and json.loads(report.read_text()).get('passed'):
    runtime_checks.append(json.loads(report.read_text()));continue
   d.mkdir(parents=True,exist_ok=True)
   if not (d/'workspace').exists():import_tree(task['starter_path'],d/'workspace')
   (d/'audit').mkdir(exist_ok=True);name='kz-v2-accept-'+secrets.token_hex(6)
   args=['run','--name',name,'--label','experiment='+R.name,'--network','none','--cpus','2','--memory','4g',
    '--user',f'{os.getuid()}:{os.getgid()}','-e','HOME=/audit','-e','PATH=/opt/node/bin:/usr/local/bin:/usr/bin:/bin','-w','/app']
   for source,target,ro in [(d/'workspace','/app',False),(d/'audit','/audit',False),(R/'runtime'/arm,'/opt/kz',True),
    (TB/'runtime/kz/node_modules','/opt/kz/node_modules',True),(TB/'runtime/node','/opt/node',True),(R/'empty-tests','/tests',True),(R/'offline_runtime.py','/opt/offline.py',True)]:
    args+=['--mount',f'type=bind,src={source},dst={target}'+(',readonly' if ro else '')]
   result=docker(*args,task['image_id'],'python3','/opt/offline.py',check=False,timeout=130)
   (d/'controller.log').write_text(result.stdout+result.stderr)
   assert docker('inspect',name,'--format','{{index .Config.Labels "experiment"}}').stdout.strip()==R.name
   docker('stop','-t','3',name,check=False);docker('rm',name)
   assert result.returncode==0,'Offline runtime failed: '+str(d)
   runtime_checks.append(json.loads(report.read_text()))
 save(R/'runtime-acceptance.json',dict(passed=all(r['passed'] for r in runtime_checks),checks=runtime_checks,model_calls=0))
 profile=json.loads((TB/'budget-profile.json').read_text())
 profile.update(campaign_limit_microcny=48_000_000,task_limit_microcny=4_000_000,
  jobs=[arm+'--'+row['task'] for row in protocol['tasks'] for arm in protocol['methods']],
  rate_basis='Peak ceiling verified in TaoToken model detail on 2026-10-18: input 2, cache 0.04, output 8 CNY/M; conservative estimate, not TokenPlan Credits invoice')
 save(R/'budget-profile.json',profile)
 subprocess.run([sys.executable,'-m','unittest','test_bounded_ledger.py'],cwd=R,check=True)
 # The exact baseline source must remain frozen, including unchanged Critic behavior.
 for name,digest in json.loads((R/'baseline-lock.json').read_text()).items():assert sha(R/'baseline'/name.replace('\\','/'))==digest
 reports=[]
 for row in protocol['tasks']:
  target=R/'fixture-grades'/('roundtrip--'+row['task'])/'result.json'
  if target.exists() and json.loads(target.read_text()).get('grading_state')!='complete':
   # Retain the failed preflight and its logs; never replace a paid artifact.
   prior=json.loads(target.read_text());exists=docker('inspect',prior['container'],check=False).returncode==0
   assert not exists,'Prior fixture container must finish cleanup before retry'
   archive=R/'fixture-failures';archive.mkdir(exist_ok=True)
   assert target.parent.resolve().is_relative_to((R/'fixture-grades').resolve())
   target.parent.rename(archive/(target.parent.name+'-'+str(time.time_ns())))
  if target.exists():report=json.loads(target.read_text())
  else:report=grade('roundtrip--'+row['task'],Path(row['starter_path']),row['starter_sha256'],fixture=True)
  name=report['container'];exists=docker('inspect',name,check=False).returncode==0
  if exists:
   assert docker('inspect',name,'--format','{{index .Config.Labels "experiment"}}').stdout.strip()==R.name
   assert docker('inspect',name,'--format','{{.State.Running}}').stdout.strip()=='false'
   docker('rm',name)
  report['grading_container_destroyed']=True;save(target,report);reports.append(report)
  save(R/'grading-acceptance.json',dict(model_calls=0,completed=len(reports),total=6,reports=reports,
    passed=len(reports)==6 and all(r['grading_state']=='complete' for r in reports)))
  print('GRADER',row['task'],report['grading_state'],flush=True)
 assert all(r['grading_state']=='complete' for r in reports),'Fix grader before paid run'
 files=[R/n for n in ['runner.py','spending.py','container-run.mjs','common.py','college_grader.py','grading_environment.py','protocol.json','budget-profile.json','input-manifest.json']]
 for arm in protocol['methods']:
  runtime=R/'runtime'/arm
  files+=list((runtime/'src').glob('*.mjs'))+list((runtime/'config').glob('*.yml'))+list((runtime/'.runtime').glob('*.yml'))+list(runtime.glob('*.mjs'))
 save(R/'ready.json',dict(passed=True,created=time.time(),model_calls=0,affected_tests=dict(baseline=111,candidate=123),
   grading_validated=6,runtime_acceptance=4,entry_acceptance=4,hashes={str(p.relative_to(R)):sha(p) for p in files},
   comparison='Same 6 tasks, paired rotating order, same provider/model/budget/critic. Only exploration differs.'))
 print('READY: 12 authorized trials, zero model calls so far')
if __name__=='__main__':main()
