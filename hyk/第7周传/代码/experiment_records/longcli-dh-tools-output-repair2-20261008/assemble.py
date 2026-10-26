"""Freeze the exact tools/no-tools ablation; no old result reuse, no mail."""
from pathlib import Path
import hashlib,json,tarfile
ROOT=Path(__file__).resolve().parent
METHODS=['dh_1234_tools']
def main():
 assert not (ROOT/'launch.claim').exists()
 p=json.loads((ROOT/'protocol.json').read_text())
 p.update(experiment=ROOT.name,methods=METHODS,total_trials=20,concurrency=6,
  concurrency_per_arm=6,native_tools_enabled={METHODS[0]:True},
  tool_names={METHODS[0]:['inspect_code','edit_code','verify_goal']},
  arms={m:{'local_correction':True,'reconnaissance':True,'critic':True,'backtracking':True} for m in METHODS},
  source=ROOT.name,
  selection='All 20 fixed LongCLIBench tasks for each arm; every trial is fresh',
  comparison='Tools repaired20 versus unchanged no-tools20 in repair1; same Docker backend, provider and all budgets; tool output handling differs explicitly',
  notifications={'enabled':False},execution_backend='college Docker only',
  container_resources={'cpu_quota':2,'visible_cpus':2,'memory_bytes':8*2**30,'pids_limit':256},
  history_results_reused=False,source_campaign='longcli-dh-tools-ablation40-20261008',
  engineering_repairs=['shared final-context projection','byte-bounded exact source pagination','full captured log retention with compact preview','explicit parameter feedback','protocol pilot stop loss'],cpu_slot_stride=2,cpu_slot_offset=0)
 assert len(p['tasks'])==20 and len({t['task'] for t in p['tasks']})==20
 (ROOT/'protocol.json').write_text(json.dumps(p,indent=2),encoding='utf-8')
 hashes={f.relative_to(ROOT).as_posix():hashlib.sha256(f.read_bytes()).hexdigest()
  for top in ('sources','compatibility') for f in (ROOT/top).rglob('*.py')}
 (ROOT/'source-provenance.json').write_text(json.dumps({'release':'DH-tools-output-repair2',
  'base_release':'DH-tools-execution-repair-v3',
  'base_arm':'1342','no_tools_source_unchanged':True,'hashes':hashes},indent=2))
 with tarfile.open(ROOT/'deployment.tar.gz','w:gz') as out:
  for top in ('sources','compatibility','tests'):
   for f in (ROOT/top).rglob('*'):
    if f.is_file() and f.suffix in {'.py','.json','.txt','.md','.toml','.yaml','.yml'} and not any(x in {'__pycache__','.pytest_cache','.git','.venv'} for x in f.parts):
     out.add(f,arcname=f.relative_to(ROOT).as_posix())
  for f in ROOT.iterdir():
   if f.is_file() and f.suffix in {'.py','.json','.ps1','.txt','.md'} and f.name not in {'ready.json','launch.json','launch.claim'}:
    out.add(f,arcname=f.name)
  for name in ('previous-rejected-candidates.json','current-failure-context.json'):
   fixture=ROOT/'evidence'/name
   assert fixture.is_file(),'Missing mandatory regression fixture: '+name
   out.add(fixture,arcname='evidence/'+name)
 print(json.dumps({'experiment':ROOT.name,'trials':20,'tasks_per_arm':20,'concurrency':6,
  'concurrency_per_arm':6,'mail_enabled':False,'sha256':hashlib.sha256((ROOT/'deployment.tar.gz').read_bytes()).hexdigest()}))
if __name__=='__main__':main()
