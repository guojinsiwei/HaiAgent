"""Transport-only bridge: original KZ JSON client -> TaoToken Messages API."""
import json,os,time,urllib.request,urllib.error
from pathlib import Path
from provider_policy import ProviderGate, ProviderQuotaUnavailable
from spending_client import SpendingClient, SpendingStopped
ENDPOINT='https://api.taotoken.net/token/v1/messages'
def payload_for(payload):
    system='\n\n'.join(m['content'] for m in payload['messages'] if m['role']=='system')
    messages=[]
    for m in payload['messages']:
        if m['role']=='system':continue
        if messages and messages[-1]['role']==m['role']:messages[-1]['content']+='\n\n'+m['content']
        else:messages.append(dict(m))
    return dict(model=payload['model'],system=system,messages=messages,max_tokens=payload['max_tokens'],
                temperature=payload['temperature'],thinking={'type':'disabled'},stream=False)
def envelope_from(value):
    # Reject native tool-use: never silently reinterpret model actions.
    content=value.get('content',[])
    if any(x.get('type')=='tool_use' for x in content):raise ValueError('Unexpected native tool use for JSON-only KZ')
    text=''.join(x.get('text','') for x in content if x.get('type')=='text')
    supplied_usage=value.get('usage')
    usage=supplied_usage if isinstance(supplied_usage,dict) else {};hit=usage.get('cache_read_input_tokens',0);write=usage.get('cache_creation_input_tokens',0)
    inp=usage.get('input_tokens',0)+hit+write;out=usage.get('output_tokens',0)
    return dict(model=value.get('model'),choices=[dict(finish_reason='stop' if value.get('stop_reason') in ('end_turn','stop_sequence') else 'length' if value.get('stop_reason')=='max_tokens' else value.get('stop_reason'),message=dict(role='assistant',content=text))],
        usage=dict(prompt_tokens=inp,completion_tokens=out,total_tokens=inp+out,prompt_cache_hit_tokens=hit,prompt_cache_miss_tokens=inp-hit) if isinstance(supplied_usage,dict) and 'input_tokens' in supplied_usage and 'output_tokens' in supplied_usage else None)
def request(endpoint,payload,key,seconds,recorder=None):
    directory=Path(recorder.path).parent if recorder is not None and hasattr(recorder,'path') else None
    gate=ProviderGate(directory)
    try:seconds=gate.before(seconds)
    except ProviderQuotaUnavailable:
        state=gate.read()
        return ('quota' if state['kind'] in ('quota','budget') else 'http'),state.get('status',429)
    except TimeoutError:return 'backoff',None
    body=payload_for(payload)
    target=os.environ.get('MODEL_MESSAGES_ENDPOINT',ENDPOINT)
    data=json.dumps(body).encode()
    req=urllib.request.Request(target,data=data,headers={'x-api-key':key,'anthropic-version':'2023-06-01','Content-Type':'application/json'})
    def budget_stop(error):
        state=dict(kind='budget',reason=str(error),status=402)
        gate.save(state)
        if directory is not None:(directory/'budget-stop.json').write_text(json.dumps(state))
        return 'quota',402
    try:
        budget=SpendingClient();started=time.monotonic();lease=budget.reserve(target,body,seconds)
        seconds=max(.1,seconds-(time.monotonic()-started))
    except SpendingStopped as error:return budget_stop(error)
    received=False
    try:
        gate.record('request')
        with urllib.request.urlopen(req,timeout=seconds) as r:result=json.loads(r.read())
        received=True
        budget.settle(lease,result.get('usage'))
        if gate.response(200,json.dumps(result)) in ('quota','credentials'):return 'quota',200
        return 'ok',json.dumps(envelope_from(result))
    except urllib.error.HTTPError as e:
        # Only classify the bounded error payload. Never persist raw bodies/headers.
        body=e.read(65536) if e.fp is not None else b''
        try:
            try:usage=json.loads(body).get('usage')
            except (ValueError,AttributeError):usage=None
            budget.settle(lease,usage)
        except SpendingStopped as error:return budget_stop(error)
        kind=gate.response(e.code,body,e.headers.get('Retry-After') if e.headers else None)
        if kind in ('quota','credentials'):return ('quota' if kind=='quota' else 'http'),e.code
        return 'http',e.code
    except SpendingStopped as error:return budget_stop(error)
    except (OSError,ValueError) as e:
        if not received:
            try:budget.settle(lease,None)
            except SpendingStopped as error:return budget_stop(error)
        gate.response(503)
        return 'error',type(e).__name__
