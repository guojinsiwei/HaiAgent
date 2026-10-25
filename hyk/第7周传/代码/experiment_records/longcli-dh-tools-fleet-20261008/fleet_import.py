"""Publish only verified remote task deliveries, never secrets or official feedback."""
import argparse,json,os
from common import ROOT,sha,save
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--job',required=True)
 ap.add_argument('--prepare',action='store_true');ap.add_argument('--commit',action='store_true');args=ap.parse_args()
 plan=json.loads((ROOT/'fleet-plan.json').read_text())
 allowed={'dh_tools--'+r['task'] for slot in ('cube0','cube1') for r in plan['assignments'][slot]}
 assert args.job in allowed
 d=ROOT/'jobs'/args.job
 assert not (d/'summary.json').exists(),'Never replace a completed task'
 if args.prepare:
  if d.exists():assert (d/'remote-transfer.json').exists(),'Refuse to overwrite a local task'
  d.mkdir(exist_ok=True);save(d/'remote-transfer.json',{'authorized':True});print('{"prepared":true}');return
 assert args.commit and (d/'remote-transfer.json').exists()
 s=json.loads((d/'fleet-incoming-summary.json').read_text())
 assert s['job']==args.job and s['state']=='awaiting_grade'
 assert sha(d/'final-source.tar.gz')==s['artifact']['sha256']
 os.replace(d/'fleet-incoming-summary.json',d/'summary.json')
 print('{"committed":true}')
if __name__=='__main__':main()
