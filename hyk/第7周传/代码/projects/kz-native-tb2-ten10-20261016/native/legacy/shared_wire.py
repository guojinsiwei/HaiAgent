"""Identical strict JSON wire for all arms. No semantic repair or action salvage."""
from dataclasses import replace
import json
import time
from urllib.error import HTTPError, URLError
from bestfgs.models import ModelCallError
from haiagent.action_protocol import strict_object
from haiagent.model import ModelError
from net_transport import request

WIRE_NOTICE = ('Transport contract: return ONE complete JSON object in the requested schema. '
               'This endpoint uses plain JSON content, not native tool calls. '
               'Do not emit DSML/XML, tool-call tags, multiple objects or partial JSON. '
               'No action in an invalid response will execute. Keep code edits small enough '
               'to fit the output limit; do not change the requested action schema.')


def correction(code):
    return ('Protocol error: '+code+'. Nothing was executed. Return ONE complete, compact JSON object. '
            'No DSML/XML/tool tags or text outside JSON. Escape strings correctly. '
            'If the output was too long, emit just one smaller command or edit chunk. '
            'Do not continue a truncated reply. No new strategy or task advice is requested.')


class SharedJSONWire:
    def __init__(self, config, audit=None, role='action', transport=None):
        self.config, self.audit, self.role = config, audit, role
        self.transport=transport or request
        self.last_failure_detail=self.last_failure_kind=None
        self.fatal_code=None
        self.stats=dict(model_calls=0,api_requests=0,api_responses=0,prompt_tokens=0,
                        completion_tokens=0,total_tokens=0,cached_prompt_tokens=0,
                        cache_miss_prompt_tokens=0,usage_reports=0,usage_missing_responses=0,
                        failure_counts={},response_models=[])

    def emit(self,event,**fields):
        if self.audit:self.audit.emit(event,role=self.role,**fields)

    def usage_summary(self):return json.loads(json.dumps(self.stats))

    def _usage(self,envelope):
        self.stats['api_responses']+=1
        usage=envelope.get('usage')
        if isinstance(usage,dict):
            self.stats['usage_reports']+=1
            for name in ('prompt_tokens','completion_tokens','total_tokens'):
                if type(usage.get(name)) is int:self.stats[name]+=usage[name]
            for target,source in (('cached_prompt_tokens','prompt_cache_hit_tokens'),
                                  ('cache_miss_prompt_tokens','prompt_cache_miss_tokens')):
                if type(usage.get(source)) is int:self.stats[target]+=usage[source]
        else:self.stats['usage_missing_responses']+=1
        model=envelope.get('model')
        if isinstance(model,str) and model not in self.stats['response_models']:
            self.stats['response_models'].append(model)

    def complete_json(self,*,system_prompt,user_prompt,history_messages=None,**unused):
        if self.fatal_code:
            self.last_failure_detail,self.last_failure_kind=self.fatal_code,'transport'
            raise ModelCallError('Terminal wire failure: '+self.fatal_code)
        self.stats['model_calls']+=1
        self.last_failure_detail=self.last_failure_kind=None
        messages=[dict(role='system',content=system_prompt+'\n'+WIRE_NOTICE),
                  *[dict(m) for m in history_messages or []],dict(role='user',content=user_prompt)]
        if any(set(m)!={'role','content'} or m['role'] not in ('system','user','assistant')
               or not isinstance(m['content'],str) for m in messages):
            raise ValueError('Only explicit text messages are accepted')
        payload=dict(model=self.config.model_name,messages=messages,stream=False,
                     temperature=self.config.temperature,max_tokens=self.config.max_tokens,
                     thinking={'type':'disabled'},response_format={'type':'json_object'})
        until=time.monotonic()+self.config.max_wall_time_seconds
        endpoint=self.config.base_url.rstrip('/')+'/chat/completions'
        for attempt in range(self.config.request_attempts):
            remaining=until-time.monotonic()
            if remaining<=0:break
            if getattr(self,'budget',None) is not None:self.budget.claim()
            self.stats['api_requests']+=1
            self.emit('wire_request',attempt=attempt+1,payload=payload)
            code='transport';kind='transport';retry=True
            status,body=self.transport(endpoint,payload,self.config.api_key,
                min(remaining,self.config.timeout_seconds),recorder=self.audit)
            if status=='ok':
                try:
                    code='invalid_response_envelope'
                    envelope=json.loads(body)
                    if not isinstance(envelope,dict):raise ValueError('envelope')
                    self._usage(envelope)
                    self.emit('wire_response',attempt=attempt+1,kind=status,envelope=envelope)
                    choices=envelope.get('choices')
                    if not isinstance(choices,list) or len(choices)!=1 or not isinstance(choices[0],dict):
                        raise ValueError('one choice')
                    choice=choices[0];message=choice.get('message')
                    if not isinstance(message,dict):raise ValueError('message')
                    reason=choice.get('finish_reason');kind='model_output'
                    code='output_length' if reason=='length' else 'nonstop_finish'
                    if reason!='stop':raise ValueError('finish reason')
                    code='empty_content';content=message.get('content')
                    if not isinstance(content,str) or not content.strip():raise ValueError('empty')
                    code='json_syntax'
                    # Only a single complete Markdown enclosure may be removed.
                    # Never extract a JSON substring from prose, DSML or a batch.
                    stripped=content.strip()
                    if stripped.startswith('```json\n') and stripped.endswith('\n```'):
                        stripped=stripped[8:-4]
                    if len(stripped)>524288:raise ValueError('content limit')
                    result=strict_object(stripped)
                    if message.get('tool_calls'):raise ValueError('mixed transport')
                    self.last_failure_detail=self.last_failure_kind=None
                    return result
                except (ValueError,TypeError,KeyError,RecursionError):pass
            else:
                self.emit('wire_response',attempt=attempt+1,kind=status,
                          status=body if type(body) is int else None)
                if status=='http' and type(body) is int:
                    code='http_'+str(body);retry=body in (408,429) or 500<=body<600
                elif status=='quota':code='provider_quota';retry=False
                elif status=='backoff':code='provider_cooldown';retry=False
                elif status=='fatal':code='transport';retry=False
            self.last_failure_detail,self.last_failure_kind=code,kind
            failures=self.stats['failure_counts'];failures[code]=failures.get(code,0)+1
            self.emit('wire_rejected',attempt=attempt+1,error_code=code,failure_kind=kind,nothing_executed=True)
            if not retry:
                if status!='backoff':self.fatal_code=code
                break
            if kind=='model_output':
                # Replace bounded correction, do not accumulate invalid replies.
                payload['messages'][-1]['content']=user_prompt+'\n'+correction(code)
        raise ModelCallError('Shared wire failed: '+str(self.last_failure_detail or 'deadline'))


class RawJSONClient:
    """RAW keeps its own prompt/history and executor, but shares the wire boundary."""
    def __init__(self,wire):self.wire=wire
    @property
    def usage(self):return self.wire.usage_summary()
    def complete(self,messages,deadline,recorder):
        messages=json.loads(json.dumps(messages))
        task=json.loads(messages[1]['content']);task['workspace']='/app'
        messages[1]['content']=json.dumps(task,ensure_ascii=False)
        remaining=deadline-time.monotonic()
        if remaining<=0:raise ModelError('task_deadline')
        self.wire.config=replace(self.wire.config,timeout_seconds=min(90,remaining),
                                  max_wall_time_seconds=min(180,remaining))
        self.wire.emit('model_request',messages=messages)
        try:
            result=self.wire.complete_json(system_prompt=messages[0]['content'],
                history_messages=messages[1:-1],user_prompt=messages[-1]['content'])
        except ModelCallError:
            code=self.wire.last_failure_detail or 'deadline'
            self.wire.emit('model_error',error_type='ModelCallError',error_code=code,
                           failure_kind=self.wire.last_failure_kind)
            if self.wire.last_failure_kind=='model_output':
                return dict(content='',complete=False,protocol_error=correction(code),
                            protocol_classification=code)
            raise ModelError(code)
        self.wire.emit('model_response',response=result,cumulative_usage=self.usage)
        return dict(content=json.dumps(result,ensure_ascii=False),complete=True)
