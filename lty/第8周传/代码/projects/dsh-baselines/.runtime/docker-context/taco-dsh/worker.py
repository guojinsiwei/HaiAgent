"""Author TACO modules, task-local pool. No network or tool implementation."""
import json
import logging
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'vendor'))
from taco_native.compression import CompressionPlanner, RuleEvolver, FeedbackCollector, DynamicCompressionFilter
from taco_native.compression.seed_rules import get_seed_rules
from taco_native.output_filter import SafeOutputFilter
from taco_native.filter_prompts import get_compress_prompt

def emit(value): print(json.dumps(value,ensure_ascii=False),flush=True)
class DiagnosticHandler(logging.Handler):
    def emit(self,record):
        message=record.getMessage()
        problem=any(word in message.lower() for word in ['failed','invalid','bad trigger','llm call'])
        emit({'type':'event','event':'algorithm_diagnostic','detail':{'severity':record.levelname,'message':message,'engineering_problem':problem}})
logging.getLogger('taco_native').addHandler(DiagnosticHandler())
instruction=''; role='taco_planner'; errors=[]

class Client:
    def chat_with_usage(self, user_content):
        emit({'type':'llm','role':role,'system':'TACO observational compression. Use the original task below as the authoritative goal.',
              'payload':{'original_task':instruction,'request':user_content}})
        reply=json.loads(sys.stdin.readline())
        if reply.get('error'):
            errors.append(reply['error']); raise RuntimeError(reply['error'])
        return reply['text'],reply.get('usage',{})

class AuditLogger:
    def __getattr__(self,name):
        def log(*args,**kwargs):
            emit({'type':'event','event':'taco_'+name,'detail':{'args':args,'kwargs':kwargs}})
        return log

client=Client(); logger=AuditLogger(); planner=CompressionPlanner(client,logger); evolver=RuleEvolver(client,logger)
feedback=FeedbackCollector(logger); filt=SafeOutputFilter(); rules=[]; episode=0; last_full=''; consumed=False

def add(rule):
    if rule is not None:
        rules.append(rule); filt.add_filter(DynamicCompressionFilter(rule))

def snapshot():
    return {'variant':'TACO task-local evolution on DSH','rules':[r.model_dump() for r in rules],
            'episode':episode,'feedback':[s.model_dump() for s in feedback.history]}

def dispatch(q):
    global instruction, role, episode, last_full, consumed
    op=q['op']
    if op=='init':
        instruction=q['instruction']; role='taco_planner'
        seeds=get_seed_rules()
        plan=planner.generate_plan(instruction,'general',q['environment'],seeds)
        for r in plan.all_active_rules()+[r.model_copy(deep=True) for r in seeds if r.rule_id in plan.selected_rule_ids]: add(r)
    elif op=='compress':
        episode+=1; raw=q['raw']; command=q['command']; last_full=raw; consumed=False
        result=filt.process(raw,command); output=result.output
        # DSH knows an actual nonzero exit even if the text error detector misses it.
        # Preserve failures and incomplete observations; no invented missing-info complaint.
        if q.get('unsafe'):
            output=raw; applied=[]
        else:
            if result.need_llm_compress and not result.is_redundant:
                role='taco_compress'
                prompt=get_compress_prompt(result.llm_compress_type).format(command=command,terminal_output=output,task_instruction=instruction)
                try:
                    response,_=client.chat_with_usage(prompt); parsed=planner._extract_json(response)
                    if parsed.get('is_safe_to_compress') and not parsed.get('has_error') and isinstance(parsed.get('summary'),str):output=parsed['summary']
                except Exception as exc:
                    emit({'type':'event','event':'compression_fallback','detail':{'error':str(exc)}})
                    output=raw
            applied=[n.removeprefix('dynamic_') for n in result.applied_filters if n.startswith('dynamic_')]
        feedback.record_compression(episode,command,raw,output,applied)
        signal=feedback.detect_uncovered(episode,command,raw,applied,threshold=3000)
        if signal and not q.get('unsafe'):
            role='taco_spawn'; add(evolver.spawn_new(signal,instruction))
        return {'output':output,'applied':applied,'state':snapshot()}
    elif op=='feedback':
        if consumed:return {'restored':None,'state':snapshot()}
        consumed=True
        signal=feedback.detect_complaint(episode,q.get('response',''),q.get('feedback',''),
            analysis=q.get('analysis',''),commands=q.get('commands',[]))
        if signal:
            role='taco_repair'
            for rid in signal.rules_applied:
                old=next((r for r in rules if r.rule_id==rid),None)
                if old:add(evolver.spawn_replacement(old,signal))
            return {'restored':last_full,'state':snapshot()}
        evolver.boost_confidence(rules,feedback._last_rules_applied)
        return {'restored':None,'state':snapshot()}
    elif op!='snapshot': raise ValueError('unknown operation')
    return snapshot()

for line in sys.stdin:
    try:
        errors.clear(); value=dispatch(json.loads(line))
        if errors: emit({'type':'event','event':'auxiliary_failure_fallback','detail':{'errors':errors}})
        emit({'type':'result','value':value})
    except Exception as exc:
        emit({'type':'event','event':'engineering_error','detail':{'message':str(exc),'kind':type(exc).__name__}})
        emit({'type':'result','error':f'{type(exc).__name__}: {exc}'})
