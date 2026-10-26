"""One all-role small budget, audit before transport, no provider-side pruning."""
import json
import hashlib
from pathlib import Path
import time
import urllib.error
import urllib.request
from common import save
from json_transport import parse_complete_object

class BudgetStop(Exception):pass
class ModelFault(Exception):pass

def envelope_bytes(messages):
    return len(json.dumps({'messages':messages},ensure_ascii=False).encode('utf-8'))

def clip_bytes(text,limit):
    if len(text.encode('utf-8'))<=limit:return text
    marker='\n[explicit budget excerpt; middle omitted; full raw evidence in audit]\n'
    raw=text.encode('utf-8');room=max(0,limit-len(marker.encode()))
    return raw[:room//2].decode('utf-8','ignore')+marker+raw[-(room-room//2):].decode('utf-8','ignore') if room else marker[:limit]

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*_):return None

class Client:
    def __init__(self,key,directory,deadline,script=None,health=None):
        self.key=key;self.directory=Path(directory);self.deadline=deadline
        self.logical=0;self.wire=0;self.usage={'prompt_tokens':0,'completion_tokens':0}
        self.script=script;self.health=health or (lambda **_:None)
        self.auxiliary_failure=None;self.responses=0

    def complete(self,messages,purpose):
        if time.monotonic()>=self.deadline:raise BudgetStop('wall_seconds')
        if self.logical>=800:raise BudgetStop('model_requests')
        if envelope_bytes(messages)>48000:raise BudgetStop('input_bytes')
        self.logical+=1
        save(self.directory/f'logical-{self.logical:04d}.json',{'purpose':purpose,'messages':messages})
        self.health(model_requests=self.logical)
        if self.script is not None:return self.script(messages,purpose)
        body={'model':'deepseek-flash','messages':messages,'temperature':0,'max_tokens':4096,
              'thinking':{'type':'disabled'},'stream':False}
        if purpose.startswith(('actor', 'lats_value')):
            body['response_format']={'type':'json_object'}
        payload=json.dumps(body,ensure_ascii=False).encode('utf-8')
        for attempt in range(2):
            if self.wire>=1600:raise BudgetStop('wire_attempts')
            remaining=self.deadline-time.monotonic()
            if remaining<=0:raise BudgetStop('wall_seconds')
            self.wire+=1;seq=self.wire
            save(self.directory/f'request-{seq:04d}.json',{'purpose':purpose,**body})
            self.health(api_attempts=self.wire)
            request=urllib.request.Request('https://api.deepseek.com/chat/completions',data=payload,
                headers={'Authorization':'Bearer '+self.key,'Content-Type':'application/json'})
            began=time.monotonic()
            try:
                with urllib.request.build_opener(NoRedirect()).open(request,timeout=min(90,remaining)) as r:
                    raw=r.read(2*1024*1024+1)
                    if len(raw)>2*1024*1024:raise ModelFault('response_bytes')
                    result=json.loads(raw)
                # Redact possible credential echoes before any durable output.
                result=json.loads(json.dumps(result,ensure_ascii=False).replace(self.key,'[REDACTED]'))
                save(self.directory/f'response-{seq:04d}.json',result)
                usage=result.get('usage',{})
                for k in self.usage:self.usage[k]+=usage.get(k,0)
                choice=result['choices'][0]
                save(self.directory/f'call-{seq:04d}.json',{'purpose':purpose,'status':200,
                    'logical_request':self.logical,'seconds':time.monotonic()-began,
                    'usage':usage,'finish_reason':choice.get('finish_reason')})
                if choice.get('finish_reason')=='length':raise ModelFault('output_tokens_exhausted')
                content=choice['message'].get('content')
                if not isinstance(content,str):raise ModelFault('missing_text')
                self.responses+=1;self.health(api_responses=self.responses)
                return content
            except urllib.error.HTTPError as exc:
                save(self.directory/f'call-{seq:04d}.json',{'purpose':purpose,'status':exc.code,'error_type':'HTTPError'})
                if exc.code in (401,402,403) or attempt==1 or exc.code not in (429,500,502,503,504):
                    raise ModelFault('http_'+str(exc.code)) from None
            except (urllib.error.URLError,TimeoutError) as exc:
                save(self.directory/f'call-{seq:04d}.json',{'purpose':purpose,'error_type':type(exc).__name__})
                if attempt==1:raise ModelFault('transport_failed') from None
        raise ModelFault('transport_failed')

    def json(self,messages,purpose):
        # One format repair is a NEW logical request; upstream-specific TACO parsers
        # operate on raw text, while our shared CLI wire remains strict.
        for attempt in range(2):
            raw=self.complete(messages,purpose if attempt==0 else purpose+'_format_repair')
            try:
                value,normalized=parse_complete_object(raw)
                if normalized:
                    save(self.directory/f'json-normalized-{self.logical:04d}.json',
                         {'purpose':purpose,'repair':'one_extra_trailing_close_brace',
                          'response_sha256':hashlib.sha256(raw.encode()).hexdigest(),
                          'command_contents_changed':False,'additional_model_calls':0})
                return value
            except (ValueError,TypeError):
                if attempt:raise ModelFault('invalid_json') from None
                messages=list(messages)+[{'role':'assistant','content':clip_bytes(raw,2000)},
                    {'role':'user','content':'Return only one complete valid JSON object matching the requested schema.'}]
        raise ModelFault('invalid_json')

    def chat_with_usage(self,*,user_content):
        before=dict(self.usage)
        try:content=self.complete([{'role':'user','content':user_content}], 'taco_auxiliary')
        except Exception as exc:
            # Author modules intentionally catch errors and use seed fallbacks.
            # The adapter must still stop on exhausted budgets or transport faults.
            self.auxiliary_failure=exc
            raise
        return content,{k:self.usage[k]-before[k] for k in self.usage}

    def check_auxiliary(self):
        if self.auxiliary_failure is not None:raise self.auxiliary_failure
