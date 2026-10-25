"""Read/write public progress only; no API credentials or model calls."""
import argparse,json,os,signal,sys,time
from pathlib import Path
from common import ROOT,save
from fleet_worker import alive

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--slot');ap.add_argument('--publish',action='store_true')
 args=ap.parse_args()
 if args.publish:
  payload=json.loads(sys.stdin.readline())
  assert payload['state'] in ('running','generation_complete','needs_attention','awaiting_credentials')
  assert payload['concurrency']==12
  plan=json.loads((ROOT/'fleet-plan.json').read_text())
  allowed={'dh_tools--'+r['task'] for slot in ('cube0','cube1') for r in plan['assignments'][slot]}
  for job,h in payload.pop('remote_live',{}).items():
   assert job in allowed
   d=ROOT/'jobs'/job
   if (d/'summary.json').exists():continue
   d.mkdir(exist_ok=True)
   save(d/'remote-transfer.json',{'authorized':True})
   save(d/'health.json',dict(h,pid=None,remote_verified_alive=True,updated=time.time()))
  save(ROOT/'health.json',dict(payload,updated=time.time()))
  receipt=json.loads((ROOT/'fleet-handoff.json').read_text())
  pid=receipt['original_controller_pid']
  legacy_done=all((ROOT/'jobs'/job/'summary.json').exists() for job in receipt['started_jobs'])
  if legacy_done and alive(pid):
   proc=Path('/proc',str(pid));assert proc.stat().st_uid==os.getuid()
   assert str(ROOT).encode() in (proc/'cmdline').read_bytes()
   os.kill(pid,signal.SIGKILL)
   save(ROOT/'fleet-legacy-controller-stopped.json',{'pid':pid,'time':time.time(),'legacy_children_completed':True})
  print('{"published":true}');return
 p=ROOT/('fleet-'+args.slot+'-health.json')
 worker=json.loads(p.read_text()) if p.exists() else {}
 rows=[]
 for d in (ROOT/'jobs').iterdir():
  sp=d/'summary.json';hp=d/'health.json'
  h=json.loads((sp if sp.exists() else hp).read_text()) if sp.exists() or hp.exists() else {}
  rows.append({'job':d.name,'summary':h if sp.exists() else None,'health':h,
      'alive':alive(h.get('pid')),'artifact_exists':(d/'final-source.tar.gz').exists()})
 lp=ROOT/('fleet-'+args.slot+'-launch.json')
 launch=json.loads(lp.read_text()) if lp.exists() else {}
 launch_pid=launch.get('pid')
 owned_alive=alive(launch_pid)
 if owned_alive:
  proc=Path('/proc',str(launch_pid))
  owned_alive=(proc.stat().st_uid==os.getuid() and b'fleet_worker.py' in (proc/'cmdline').read_bytes())
 print(json.dumps({'worker':worker,'jobs':rows,'launch':launch,
     'launch_alive':owned_alive,'launch_claim_exists':(ROOT/('fleet-'+args.slot+'-launch.claim')).exists()}))

if __name__=='__main__':main()
