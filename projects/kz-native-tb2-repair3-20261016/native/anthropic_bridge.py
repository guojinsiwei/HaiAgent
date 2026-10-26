"""Transport-only bridge: original KZ JSON client -> TaoToken Messages API."""
import json,os,time,urllib.request,urllib.error,hashlib
from pathlib import Path
from provider_policy import ProviderGate, ProviderQuotaUnavailable
from spending_client import SpendingClient, SpendingStopped
ENDPOINT='https://api.taotoken.net/token/v1/messages'

def request(endpoint,payload,key,seconds,recorder=None):
    directory=Path(recorder.path).parent if recorder is not None and hasattr(recorder,'path') else None
    gate=ProviderGate(directory)
    try:seconds=gate.before(seconds)
    except ProviderQuotaUnavailable:
        state=gate.read()
        if state.get('kind')=='accounting':return 'fatal',None
        return ('quota' if state.get('kind') in ('quota','budget') else 'http'),state.get('status',429)
    except TimeoutError:return 'backoff',None
    body=payload_for(payload);target=os.environ.get('MODEL_MESSAGES_ENDPOINT',ENDPOINT)
    req=urllib.request.Request(target,data=json.dumps(body).encode(),headers={'x-api-key':key,'anthropic-version':'2023-06-01','Content-Type':'application/json'})
    budget=SpendingClient()
    def stop(error):
        reason=str(error);kind='budget' if reason in ('per_task_budget_exhausted','per_task_request_limit','campaign_budget_exhausted') else 'accounting'
        state=dict(kind=kind,reason=reason,origin='local_accounting')
        gate.save(state)
        if directory is not None:(directory/'budget-stop.json').write_text(json.dumps(state))
        gate.record('local_stop',reason=reason,kind=kind)
        return ('quota',None) if kind=='budget' else ('fatal',None)
    def settle(lease,usage):
        try:budget.settle(lease,usage);return None
        except SpendingStopped as error:
            if str(error)!='usage_unavailable':return stop(error)
            # The ledger keeps the FULL reservation. Permit one uncertain
            # response per trial; a second stops this trial, not the campaign.
            path=directory/'usage-recovery.json' if directory is not None else None
            state=json.loads(path.read_text()) if path is not None and path.exists() else {}
            count=state.get('unknown_responses',0)+1
            if path is not None:path.write_text(json.dumps(dict(unknown_responses=count,max_unknown_responses=2)))
            gate.record('uncertain_usage_retained',unknown_responses=count,recovery_allowed=count<2)
            return None if count<2 else stop(error)
    try:
        started=time.monotonic();lease=budget.reserve(target,body,seconds)
        seconds=max(.1,seconds-(time.monotonic()-started))
    except SpendingStopped as error:return stop(error)
    gate.record('request')
    try:
        with urllib.request.urlopen(req,timeout=seconds) as response:
            raw=response.read();status=response.status
    except urllib.error.HTTPError as error:
        raw=error.read(65536) if error.fp is not None else b''
        status=error.code
        kind=gate.response(status,raw,error.headers.get('Retry-After') if error.headers else None)
        gate.record('http_failure',status=status,body_bytes=len(raw),body_sha256=hashlib.sha256(raw).hexdigest())
        try:value=json.loads(raw);usage=value.get('usage') if isinstance(value,dict) else None
        except (ValueError,TypeError):usage=None
        halted=settle(lease,usage)
        if halted:return halted
        return ('quota' if kind=='quota' else 'http'),status
    except (OSError,ValueError) as error:
        gate.record('transport_failure',error_type=type(error).__name__)
        gate.response(503)
        halted=settle(lease,None)
        return halted if halted else ('error',type(error).__name__)
    gate.record('http_response',status=status,body_bytes=len(raw),body_sha256=hashlib.sha256(raw).hexdigest())
    try:
        value=json.loads(raw)
        if not isinstance(value,dict):raise ValueError('response must be object')
    except (ValueError,TypeError) as error:
        gate.record('invalid_envelope',error_type=type(error).__name__)
        gate.response(503)
        halted=settle(lease,None)
        return halted if halted else ('error','invalid_response_envelope')
    halted=settle(lease,value.get('usage'))
    if halted:return halted
    kind=gate.response(status,raw)
    if kind in ('quota','credentials'):return ('quota' if kind=='quota' else 'http'),status
    try:return 'ok',json.dumps(envelope_from(value))
    except (ValueError,TypeError,KeyError) as error:
        gate.record('invalid_envelope',error_type=type(error).__name__)
        return 'error','invalid_response_envelope'
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
