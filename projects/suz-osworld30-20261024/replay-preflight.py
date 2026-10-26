"""Offline full protocol replay; original screenshots/outputs never altered."""
import json,sys,os,time
from pathlib import Path
from common import ROOT,SOURCE,config,source_hash,deployment_hash
sys.path.insert(0,str(SOURCE))
from python.suz_agent import SUZAgent
from python.runtime import MeteredClient
class Replay:
 def __init__(self,rows,cfg,destination):
  self.rows=rows;self.index=0;self.spent=0;self.calls=[];self.live=None;self.cfg=cfg;self.destination=destination;self.live_count=0
 def complete(self,role,payload):
  # Accepted planning changes memory retrieval and the exact frames supplied to
  # Critic. Obtain a fresh review of that actual context, never rewrite citations.
  if role=='critic' and json.loads(payload['messages'][1]['content'][0]['text']).get('stage')=='review':
   if self.index<len(self.rows):
    assert self.rows[self.index]['role']=='critic';self.index+=1
   assert self.live_count<2
   if self.live is None:
    os.environ['SUZ_API_KEY']=(ROOT/'secrets/api-key').read_text().strip()
    self.live=MeteredClient(self.cfg,self.destination/'fresh-critic')
   self.live_count+=1;result=self.live.complete(role,payload)
   self.spent=self.live.spent;self.calls.append({'role':role,'live':True});return result
  assert self.index<len(self.rows),'unexpected new request'
  row=self.rows[self.index];assert row['role']==role,(self.index,row['role'],role)
  self.index+=1;self.calls.append({'role':role});choice=row['choices'][0]
  assert choice['finish_reason']=='stop';return choice['message']['content']
results=[]
for mode in ['opencua_baseline','suz']:
 original=ROOT/'preflight-multistep'/mode
 destination=ROOT/'preflight-protocol-replay-final'/mode
 raw=[json.loads(x) for x in (original/'model-responses.jsonl').read_text().splitlines()]
 predictions=[json.loads(x) for x in (original/'agent.jsonl').read_text().splitlines() if json.loads(x)['event']=='prediction']
 old=json.loads((original/'controller.json').read_text())
 cfg=config('multistep-v2',mode,'preflight-multistep')
 client=Replay(raw,cfg,destination);agent=SUZAgent(cfg,destination,client=client,node=str(ROOT/'.venv/bin/node'))
 try:
  for index,expected in enumerate(predictions):
   frame=original/'frames'/f'F{index}.png'
   _,actions,info=agent.predict(old['instruction'],{'screenshot':frame.read_bytes()},step_idx=index)
   assert actions==expected['actions'],(index,actions,expected['actions'])
   if actions not in (['DONE'],['FAIL']):agent.record_feedback('unknown','desktop returned screenshot')
  state=agent.bridge.call('snapshot');assert not state['roleErrors'],state['roleErrors']
  assert actions==['DONE'];assert client.index==len(raw),(client.index,len(raw))
  if mode=='suz':
   assert state['review']['accepted']
   assert len(state['memoryEffects'])>0
   assert sum(e['type']=='role_applied' and e.get('role')=='monitor' for e in state['events'])>=2
  row={'mode':mode,'passed':True,'model_calls':client.live_count,'new_cost_cny':client.spent,'recorded_requests':len(raw),'identical_action_batches':len(predictions),'role_errors':state['roleErrors'],'source_sha256':source_hash(),'deployment_sha256':deployment_hash(),'validation_kind':'real_CPU_multistep_trace_plus_full_protocol_replay_and_fresh_final_critic'}
  results.append(row);print(json.dumps(row),flush=True)
 finally:agent.close()
(ROOT/'preflight-protocol-replay-final/result.json').write_text(json.dumps(results,indent=2))
