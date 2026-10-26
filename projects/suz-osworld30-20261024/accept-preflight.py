"""Accept explicit hybrid evidence; never relabel failed original preflights."""
import hashlib,json,tarfile,time
from PIL import Image
from common import ROOT,SOURCE,source_hash,deployment_hash
replay=json.loads((ROOT/'preflight-protocol-replay-final/result.json').read_text())
assert len(replay)==2 and {r['mode'] for r in replay}=={'suz','opencua_baseline'}
with tarfile.open(ROOT/'source-before-memory-list-fix.tar.gz') as archive:
 before={m.name.split('/',1)[1]:archive.extractfile(m).read() for m in archive.getmembers() if m.isfile() and '__pycache__' not in m.name}
after={p.relative_to(SOURCE).as_posix():p.read_bytes() for p in SOURCE.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
assert before.keys()==after.keys()
changed=sorted(k for k in before if before[k]!=after[k])
assert changed==['src/controller.mjs','tests/controller.test.mjs'],changed
oldhash=hashlib.sha256()
for name in sorted(before):oldhash.update(name.encode());oldhash.update(before[name])
original=ROOT/'preflight-multistep'
base=json.loads((original/'opencua_baseline/result.json').read_text())
assert base['passed'] and base['source_sha256']==oldhash.hexdigest()
arms=[]
for row in replay:
 assert row['passed'] and row['source_sha256']==source_hash() and row['deployment_sha256']==deployment_hash()
 assert row['identical_action_batches']>=5 and not row['role_errors']
 p=original/row['mode'];state=json.loads((p/'controller.json').read_text())
 assert state['halted'] in {'visually_accepted','solver_declared_done'}
 if row['mode']=='suz':
  assert state['review']['accepted']
  assert state['roleErrors']==[{'role':'planner','reason':'memory_review must cite currently visible M IDs','step':5}]
  assert row['model_calls'] in [1,2]
 with Image.open(p/'last-observation.png') as im:
  pixels=list(im.convert('RGB').resize((96,54)).getdata())
  green=sum(g>130 and r<40 and 40<b<140 for r,g,b in pixels)/len(pixels)
 assert green>.45
 arms.append({**row,'cpu_only':True,'green_fraction':green,'original_live_source_sha256':oldhash.hexdigest(),
  'evidence_directory':str(p),'replay_directory':str(ROOT/'preflight-protocol-replay-final'/row['mode'])})
result={'source_sha256':source_hash(),'deployment_sha256':deployment_hash(),'arms':arms,'timestamp':time.time(),
 'validation_kind':'real_CPU_multistep_trace_plus_full_protocol_replay_and_fresh_final_critic',
 'changed_since_live_preflight':changed,'original_live_errors_preserved':True,
 'scope':'Protocol compatibility verified with recorded outputs; live behavior under new planning remains to be measured in the formal experiment.'}
target=original/'passed.json';assert not target.exists()
target.write_text(json.dumps(result,indent=2));print(json.dumps(result))
