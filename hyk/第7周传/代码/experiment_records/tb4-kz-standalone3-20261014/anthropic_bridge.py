"""Transport-only bridge: original KZ JSON client -> TaoToken Messages API."""
import json,urllib.request,urllib.error
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
    usage=value.get('usage') or {};hit=usage.get('cache_read_input_tokens',0);write=usage.get('cache_creation_input_tokens',0)
    inp=usage.get('input_tokens',0)+hit+write;out=usage.get('output_tokens',0)
    return dict(model=value.get('model'),choices=[dict(finish_reason='stop' if value.get('stop_reason') in ('end_turn','stop_sequence') else 'length' if value.get('stop_reason')=='max_tokens' else value.get('stop_reason'),message=dict(role='assistant',content=text))],
        usage=dict(prompt_tokens=inp,completion_tokens=out,total_tokens=inp+out,prompt_cache_hit_tokens=hit,prompt_cache_miss_tokens=inp-hit))
def request(endpoint,payload,key,seconds,recorder=None):
    data=json.dumps(payload_for(payload)).encode()
    req=urllib.request.Request(ENDPOINT,data=data,headers={'x-api-key':key,'anthropic-version':'2023-06-01','Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(req,timeout=seconds) as r:result=json.loads(r.read())
        return 'ok',json.dumps(envelope_from(result))
    except urllib.error.HTTPError as e:
        # Never log HTTP headers or credential-bearing objects.
        return 'http',e.code
    except (OSError,ValueError) as e:return 'error',type(e).__name__
