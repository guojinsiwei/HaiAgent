"""Budget-charged transport repairs only; installed in isolated recovery copies."""
import json
import math
import time

NOTICE = ('Return one COMPLETE compact response within the existing output-token limit. '
          'For JSON, escape all double quotes and newlines INSIDE string values. '
          'Write code using small edits or short chunks; never emit an entire large file. '
          'Do not repeat array entries. No command from a rejected response has executed.')


def taco_timeout(requested):
    if isinstance(requested,bool) or not isinstance(requested,(int,float)) or not math.isfinite(requested):
        return 300
    return min(300,max(1,requested))


def taco_cache_path(directory):
    return directory/'taco-rules.json'


def with_notice(messages, notice=NOTICE):
    result=[dict(m) for m in messages]
    result[-1]['content'] += '\n\n'+notice
    return result


def install_small():
    import client
    original=client.Client.complete
    def complete(self,messages,purpose):
        base=with_notice(messages)
        for attempt in range(3):
            try:
                return original(self,base,purpose if attempt==0 else purpose+'_length_repair')
            except client.ModelFault as exc:
                if str(exc)!='output_tokens_exhausted' or attempt==2:raise
                # original() increments the same logical/wire counters each time.
                client.save(self.directory/f'length-repair-{self.logical:04d}.json',
                    {'purpose':purpose,'attempt':attempt+1,'nothing_executed':True})
                base=with_notice(messages,NOTICE+' Previous output was cut off. '
                    'Regenerate from scratch, at most 1200 tokens; one small command/edit or minimal rule. '
                    'For a rule, use at most 5 distinct patterns. Do not continue the cut-off response.')
    client.Client.complete=complete
    original_json=client.Client.json
    # Existing JSON/schema parsers and their attempts remain in force.
    return {'small_length_attempts':3,'all_repairs_count_toward_original_budget':True}


def install_retrac():
    import matched_adapter as a
    import runner
    old_event_failure=runner.event_failure
    def event_failure(event,payload):
        if event=='invalid_action' and payload.get('attempt',0)<3:return None
        return old_event_failure(event,payload)
    runner.event_failure=event_failure
    from retrac.engine import ProtocolError,parse_action
    old_open=a.MatchedClient._open
    def opened(self,request,timeout):
        body=json.loads(request.data)
        if self.current_purpose=='act':
            body['response_format']={'type':'json_object'}
            request.data=json.dumps(body,ensure_ascii=False).encode()
        return old_open(self,request,timeout)
    a.MatchedClient._open=opened
    def action(self,messages,record):
        base=with_notice(messages)
        for attempt in range(3):
            reply=self._complete(base,'act',record)
            try:
                if reply.finish_reason=='length':raise ProtocolError('Output was truncated')
                normalized,repaired=a.normalize_action_transport(reply.content)
                value=parse_action(normalized,self.config.max_command_duration)
            except ProtocolError as exc:
                self._log('invalid_action',round=record.index,error=str(exc),attempt=attempt+1)
                if attempt==2:raise
                base=with_notice(messages,NOTICE+' Invalid JSON/schema: '+str(exc)+'. '
                    'Use all four fields: analysis (brief), commands (array), task_complete (boolean), '
                    'final_answer (string). Keep the command under 1500 characters. '
                    'Avoid embedding C/Python source with unescaped quotation marks. '
                    'Use a small shell edit; JSON strings must escape every inner double quote.')
            else:
                if repaired:self._log('action_transport_normalized',round=record.index,commands_changed=False)
                messages.append({'role':'assistant','content':normalized})
                return value
        raise AssertionError('unreachable')
    a.MatchedRunner._action=action
    return {'json_mode':'actions_only','action_parse_attempts':3,'original_model_budget':800}


def install_dh():
    import budget_adapter as b
    import bestfgs.lean_conversation as conversation
    original_estimate=b.estimated_tokens
    scale=[1.5]
    def estimate(messages):return math.ceil(original_estimate(messages)*scale[0])
    b.estimated_tokens=estimate
    # install_context_meter uses the calibrated estimate for native history selection.
    old_call=b.CheckedTransport.__call__
    def checked(self,endpoint,payload,key,seconds,recorder=None):
        messages=payload['messages'];removed=0
        # Also cover correction messages added after native history projection.
        while estimate(messages)+65536>1000000 and len(messages)>2:
            del messages[1: min(3,len(messages)-1)];removed+=1
        if removed:
            self.audit.emit('transport_history_projection',removed_old_pairs=removed,
                reason='calibrated_token_allowance',full_history_retained_in_audit=True)
        raw_estimate=original_estimate(messages)
        result=old_call(self,endpoint,payload,key,seconds,recorder)
        if result[0]=='ok':
            try:actual=json.loads(result[1])['usage']['prompt_tokens']
            except (KeyError,TypeError,ValueError):actual=None
            if type(actual) is int and raw_estimate:
                new=max(scale[0],actual/raw_estimate*1.10)
                if new>scale[0]:
                    scale[0]=new
                    self.audit.emit('token_meter_calibration',actual_input_tokens=actual,
                        baseline_estimate=raw_estimate,scale=new,exact_tokenizer=False)
        return result
    b.CheckedTransport.__call__=checked
    return {'token_meter_initial_safety_factor':1.5,'calibrate_from_provider_usage':True,
            'context_allowance':1000000,'headroom':65536,'wire_attempt_limit':800}


def install_taco():
    """Keep TACO rules within one task and normalize only the CLI timeout bound."""
    report=install_small()
    import agents
    import runner
    from common import save
    original_action=agents.action
    original_linear=runner.linear

    def bounded_action(client,*args,**kwargs):
        result=original_action(client,*args,**kwargs)
        if result.get('action')!='run':return result
        requested=result.get('timeout_seconds')
        effective=taco_timeout(requested)
        if requested==effective and type(requested) in (int,float):return result
        result=dict(result,timeout_seconds=effective)
        save(client.directory/f'timeout-normalized-{client.logical:04d}.json',
             {'requested_type':type(requested).__name__,'effective_seconds':effective,
              'reason':'sandbox_timeout_range_1_to_300','model_calls':0})
        return result

    def task_local_linear(client,env,instruction,taco=False,cache_path=None):
        if taco:cache_path=taco_cache_path(env.directory)
        return original_linear(client,env,instruction,taco=taco,cache_path=cache_path)

    agents.action=bounded_action
    runner.linear=task_local_linear
    report.update(task_local_rule_cache=True,timeout_normalized_to_sandbox_bound=True,
                  command_and_tool_budgets_unchanged=True)
    return report


def install_lats():
    """Keep author search intact while bounding requested CLI timeouts to sandbox policy."""
    report=install_small()
    import sandbox
    from common import save
    original_execute=sandbox.Sandbox.execute

    def bounded_execute(self,action):
        requested=action.get('timeout_seconds',300)
        effective=taco_timeout(requested)
        if requested!=effective or type(requested) not in (int,float):
            action=dict(action,timeout_seconds=effective)
            save(self.directory/'timeout-normalizations'/f'{time.time_ns()}.json',
                 {'requested_type':type(requested).__name__,'effective_seconds':effective,
                  'reason':'sandbox_timeout_range_1_to_300','model_calls':0})
        return original_execute(self,action)

    sandbox.Sandbox.execute=bounded_execute
    report.update(timeout_normalized_to_sandbox_bound=True,
                  search_and_model_budgets_unchanged=True)
    return report


def install(method):
    if method=='retrac':return install_retrac()
    if method=='dh':return install_dh()
    if method=='taco':return install_taco()
    if method=='lats':return install_lats()
    return install_small()
