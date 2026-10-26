"""Exercise actual transport input/output ceilings without network or API keys."""
import json
import environment  # Install the packaged source and compatibility import paths.
from budget_adapter import CheckedTransport,WireBudget
class Audit:
    def emit(self,*args,**kwargs):pass
def main():
    calls=[]
    t=CheckedTransport(Audit(),transport=lambda e,p,k,s,recorder=None:calls.append(p) or ('ok','{}'))
    payload={'max_tokens':4096,'messages':[{'role':'system','content':'s'},
        {'role':'user','content':'older'*14000},{'role':'assistant','content':'reply'},
        {'role':'user','content':'protected memory'+('中'*8000)}]}
    t('fixture',payload,'fixture',1)
    assert len(json.dumps({'messages':calls[-1]['messages']},ensure_ascii=False).encode('utf-8'))<=48000
    assert calls[-1]['messages'][-1]['content']==payload['messages'][-1]['content']
    try:t('fixture',{'max_tokens':32768,'messages':[{'role':'user','content':'x'}]},'fixture',1)
    except AssertionError:pass
    else:raise AssertionError('wrong output cap admitted')
    b=WireBudget(2);b.claim();b.claim()
    try:b.claim()
    except TimeoutError:pass
    else:raise AssertionError('budget bypass')
    print(json.dumps({'input_bytes_max':48000,'output_tokens':4096,'shared_request_cap_verified':True,
        'paid_model_calls':0,'passed':True}))
if __name__=='__main__':main()
