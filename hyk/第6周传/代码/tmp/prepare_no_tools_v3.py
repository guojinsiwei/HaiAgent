"""Archive exactly three interrupted attempts, then hand off only the broken controller."""
import json,os,signal,time
from pathlib import Path
from no_tools_supervisor_v3 import ROOT,process_status
import sys
sys.path.insert(0,str(ROOT))
from common import save,validate
TARGETS=('cs61_fa24_ants','cmu15_445_p0','ap1400_2_hw26')
def main():
 validate()
 marker=ROOT/'supervisor-v3-preparation.json'
 if marker.exists():print(marker.read_text());return
 old=json.loads((ROOT/'health.json').read_text());pid=old['pid']
 status=process_status(pid,expected_start='735490617')
 if status['status']=='running':
  assert b'resume_no_tools_supervisor.py' in Path('/proc',str(pid),'cmdline').read_bytes()
  os.kill(pid,signal.SIGKILL) # PID only, never the process group or its cow child.
 elif status['status'] not in ('exited','reused','foreign'):raise RuntimeError('controller_identity_uncertain')
 # Validate ALL targets before moving any. No live task may be archived.
 for task in TARGETS:
  d=ROOT/'jobs'/('dh_1234_no_tools--'+task);s=json.loads((d/'summary.json').read_text())
  assert s['stop_reason']=='supervisor_fault'
  assert process_status(s.get('pid'))['status'] in ('exited','foreign','reused')
  assert (d/'final-source.tar.gz').is_file()
 moves=[];archive=ROOT/'retry-archive/supervisor-v2-failure'
 for task in TARGETS:
  job='dh_1234_no_tools--'+task
  for group in ('jobs','grades','incoming'):
   src=ROOT/group/job;dst=archive/group/job
   assert src.resolve().is_relative_to(ROOT.resolve()) and dst.resolve().is_relative_to(ROOT.resolve())
   if src.exists():
    assert not dst.exists();dst.parent.mkdir(parents=True,exist_ok=True);src.rename(dst)
    moves.append({'source':str(src),'archived':str(dst)})
 cow=ROOT/'jobs/dh_1234_no_tools--61810_cow';cow_done=(cow/'summary.json').exists()
 h=json.loads((cow/'health.json').read_text());cow_live=process_status(h.get('pid'))['status']=='running'
 pending=[];completed=[]
 for row in json.loads((ROOT/'protocol.json').read_text())['tasks']:
  job='dh_1234_no_tools--'+row['task'];d=ROOT/'jobs'/job
  if (d/'summary.json').exists():completed.append(job)
  elif not (d/'health.json').exists():pending.append(job)
 receipt={'time':time.time(),'old_controller_retired':True,'archived_attempts':list(TARGETS),
  'moves':moves,'cow_running_preserved':cow_live,'cow_already_finished':cow_done,
  'source_unchanged':True,'pending_count':len(pending),'normal_results_preserved':len(completed)}
 save(marker,receipt)
 save(ROOT/'health.json',{'state':'needs_attention','controller_state':'awaiting_v3_secure_launch',
  'pid':None,'updated':time.time(),'active':['dh_1234_no_tools--61810_cow'] if cow_live else [],
  'pending':pending,'completed':completed,'errors':[{'reason':'supervisor_v2_retired_repair_ready'}],
  'retired_methods':['dh_1234_tools']})
 print(json.dumps(receipt))
if __name__=='__main__':main()
