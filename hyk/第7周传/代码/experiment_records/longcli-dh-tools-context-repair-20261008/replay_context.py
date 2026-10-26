"""Offline replay of historical failing-run prompt pressure. Outputs sizes only."""
import json
from pathlib import Path
import environment
from bestfgs.context_budget import fit_payload,message_bytes
from bestfgs.lean_conversation import Conversation
from common import ROOT,save
OLD=Path('/var/tmp/longcli-dh-tools-small20-20261008')
def main():
    calls=0;errors=[];peak=0
    for task in ('cs61_fa24_hog','ap1400_2_hw35','cmu15_445_p1','cs61_fa24_ants','61810_fs'):
        c=Conversation(byte_budget=True);path=OLD/'jobs'/('dh_tools--'+task)/'trace/events.jsonl'
        for line in path.open():
            e=json.loads(line)
            if e.get('event')=='conversation_turn':c.append(e['action'],e['feedback'],e.get('context'))
            if e.get('event')!='final_prompt':continue
            ms=e.get('messages',[])
            if len(ms)<2:continue
            p=json.loads(ms[-1]['content']);system=ms[0]['content']
            try:
                projected,stats=fit_payload(system,p,44976)
                h,v=c.build(system,projected,44976)
                n=message_bytes([{'role':'system','content':system},*h,
                    {'role':'user','content':json.dumps(projected,ensure_ascii=False)}])
                assert n<=44976;peak=max(peak,n);calls+=1
            except Exception as error:errors.append({'task':task,'event':e['seq'],'type':type(error).__name__})
    result={'replayed_requests':calls,'errors':errors,'peak_input_bytes':peak,'paid_model_calls':0,
        'passed':not errors,'scope':'historical prompts and accumulated original conversation'}
    save(ROOT/'evidence/context-replay.json',result);print(json.dumps(result))
    assert not errors
if __name__=='__main__':main()
