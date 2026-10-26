"""Report matched fresh runs separately from mixed-version historical cumulative data."""
from pathlib import Path
import json,time
R=Path(__file__).resolve().parent;H=R.parent
def read(p):
 try:return json.loads(p.read_text())
 except (FileNotFoundError,ValueError):return {}
def main():
 import subprocess
 tb=json.loads(subprocess.check_output(['python3',str(H/'tb2-hld-recuris50-20261020/effective_status.py')],text=True))
 prior=read(H/'swepro-hld-ab5-20261020/health.json')
 tb_state=tb.get('state','preparing')
 if tb_state=='held_low_disk' and prior.get('state')=='running' and prior.get('concurrency',0)>0:
  tb_state='waiting_for_existing_swepro_comparison'
 aw=H/'appworld-hld-recuris70-20261020'
 hist=read(R/'historical-appworld30.json')['selected']
 rows=[read(p) for p in (aw/'jobs').glob('*/summary.json')]
 app={}
 for a in ['hld','recuris']:
  old=[x for x in hist if x['arm']==a];new=[x for x in rows if x.get('arm')==a and not (aw/'jobs'/x['job']/'user-stop.json').exists()]
  scored=[x for x in new if x.get('grading')=='complete']
  app[a]=dict(new_target=70,new_finished=len(new),new_scored=len(scored),new_passed=sum(x.get('official_success') is True for x in scored),
   new_engineering_faults=sum(bool(x.get('engineering_fault')) for x in new),historical_tasks=30,historical_cumulative_passed=sum(x['success'] is True for x in old),
   historical_attempts=sum(x['attempt_count'] for x in old),combined_target=100,combined_scored=30+len(scored),
   combined_mixed_version_cumulative_passed=sum(x['success'] is True for x in old)+sum(x.get('official_success') is True for x in scored))
 out=dict(updated=time.time(),paused_arms=['hld'],enabled_arms=['recuris'],tb2=dict(state=tb_state,raw_controller_state=tb.get('state'),arms=tb.get('summary'),active=len(tb.get('active',[])),budget=tb.get('spending')),
  appworld=dict(state=read(aw/'health.json').get('state','preparing'),arms=app,concurrency=read(aw/'health.json').get('concurrency',0),budget=read(aw/'health.json').get('budget')),
  interpretation='AppWorld combined100 uses historical retained passes after selective reruns plus fresh new70. Mixed versions and attempt counts; not latest-HLD pass@1. HLD paused by user; fresh runs now continue for Recuris only. User-interrupted HLD runs excluded.')
 (R/'status.json').write_text(json.dumps(out,indent=2,ensure_ascii=False));print(json.dumps(out,indent=2,ensure_ascii=False))
if __name__=='__main__':main()
