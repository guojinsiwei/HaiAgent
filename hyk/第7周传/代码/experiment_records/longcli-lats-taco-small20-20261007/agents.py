"""Explicitly labelled paper CLI adapters; no privileged online benchmark feedback."""
from dataclasses import dataclass,field
import json
import math
from pathlib import Path
import shlex
from common import save
from client import BudgetStop,ModelFault,clip_bytes,envelope_bytes

ACTION_SCHEMA = ('Return JSON {"analysis":"brief","action":"run|submit",'
    '"argv":["sh","-c","command"],"cwd":".","stdin":"",'
    '"timeout_seconds":300,"summary":"","compression_feedback":""}. '
    'One command per reply. For submit, argv can be empty. No Markdown. '
    'Read INSTRUCTION.md on disk. Every command has a fresh shell; persistent '
    'background processes are killed. Work under /app. Network disabled. '
    'Hidden benchmark tests and scores are unavailable. Verify using public '
    'specification and your own tests before submission. Output limit4096 tokens.')

def messages(instruction,history,system,extra=''):
    # Same explicit history projection for both methods. No deletion at provider.
    prefix='Task: '+instruction+'\n'+extra+'\nObserved trajectory:\n'
    rows=list(history)
    def build():
        return [{'role':'system','content':system}, {'role':'user','content':prefix+json.dumps(rows,ensure_ascii=False)}]
    result=build();omitted=0
    while envelope_bytes(result)>46000 and len(rows)>1:
        rows.pop(0);omitted+=1;result=build()
    if envelope_bytes(result)>46000 and rows:
        # Excerpt only observation text; retain action and exit code intact.
        row=dict(rows[-1]);row['observation']=clip_bytes(str(row.get('observation','')),18000)
        rows[-1]=row;result=build()
    if omitted:
        result[1]['content']='[Explicit history budget: '+str(omitted)+' older exchanges omitted; audit retains them]\n'+result[1]['content']
    if envelope_bytes(result)>48000:raise BudgetStop('input_bytes')
    return result

def action(client,instruction,history,extra=''):
    result=client.json(messages(instruction,history,ACTION_SCHEMA,extra),'actor')
    if not isinstance(result,dict) or result.get('action') not in ('run','submit'):
        raise ModelFault('action_schema')
    if result['action']=='run' and (not isinstance(result.get('argv'),list) or not result['argv']):
        raise ModelFault('action_argv')
    return result

def observation(result):
    return 'Exit code: '+str(result['exit_code'])+'\nSTDOUT:\n'+result['stdout']+'\nSTDERR:\n'+result['stderr']

@dataclass
class Node:
    checkpoint:dict
    history:list
    parent:object=None
    children:list=field(default_factory=list)
    depth:int=0
    prior:float=0.0
    value:float=0.0
    visits:int=0
    terminal:bool=False
    public_verified:bool=False

    def uct(self,w=1):
        if self.visits==0:return float('inf')
        return self.value/self.visits+w*math.sqrt(math.log(max(1,self.parent.visits))/self.visits)

def backprop(node,reward):
    while node is not None:
        node.visits+=1;node.value+=reward;node=node.parent

def lats(client,env,instruction,settings):
    root=Node(env.checkpoint('root'),[]);nodes=[root];reflections=[];events=[]
    best=root;reason='rollout_limit';submitted=False
    samples=settings['samples'];weight=settings['value_weight']

    def review(node,terminal):
        nonlocal best
        system=('Evaluate observed CLI progress against the public specification. No hidden tests. '
            'Return JSON {"score":0.0,"complete":false,"verification":null,"feedback":"brief"}. '
            'score is finite in[0,1]. If complete, verification MUST be an independent public-only '
            'shell command (argv/cwd/stdin/timeout_seconds) that checks the claimed outcome; '
            'never merely echo a success label. No destructive commands.')
        r=client.json(messages(instruction,node.history,system,
                     'Failed-trajectory reflections: '+json.dumps(reflections[-3:])),'lats_value')
        if not isinstance(r,dict):raise ModelFault('value_schema')
        score=r.get('score')
        if isinstance(score,bool) or not isinstance(score,(float,int)) or not math.isfinite(score) or not 0<=score<=1:
            raise ModelFault('value_schema')
        verified=False
        if terminal and r.get('complete') is True and isinstance(r.get('verification'),dict):
            check=env.execute(r['verification'])
            node.history=node.history+[{'action':r['verification'],'observation':clip_bytes(observation(check),24000),
                                      'internal_verification':True}]
            node.checkpoint=env.checkpoint('public-check')
            verified=check['exit_code']==0 and not check['timed_out']
        node.public_verified=verified
        events.append({'event':'value','depth':node.depth,'lm_score':score,'public_verified':verified})
        return float(score),str(r.get('feedback',''))

    def expand(node):
        counts={};actions={};order=[]
        for _ in range(samples):
            a=action(client,instruction,node.history,'Failure reflections: '+json.dumps(reflections[-3:]))
            signature=json.dumps({k:a.get(k) for k in ('action','argv','cwd','stdin','timeout_seconds')},sort_keys=True)
            if signature not in counts:order.append(signature);actions[signature]=a;counts[signature]=0
            counts[signature]+=1
        events.append({'event':'expansion','depth':node.depth,'samples':samples,'unique':len(order)})
        for signature in order:
            env.restore(node.checkpoint)
            a=actions[signature];history=list(node.history);terminal=a['action']=='submit'
            if terminal:
                history.append({'action':a,'observation':'Model requested submission; this is NOT benchmark success.'})
            else:
                result=env.execute(a)
                history.append({'action':a,'observation':clip_bytes(observation(result),24000)})
            child=Node(env.checkpoint('child'),history,parent=node,depth=node.depth+1,terminal=terminal)
            score,_=review(child,terminal)
            child.prior=weight*score+(1-weight)*(counts[signature]/samples)
            node.children.append(child);nodes.append(child)
        events.append({'event':'evaluated_children','scores':[c.prior for c in node.children]})
        return max(node.children,key=lambda c:(c.public_verified,c.prior))

    try:
        for rollout in range(settings['rollouts']):
            node=root
            while node.children and not node.terminal and node.depth<settings['depth']:
                candidates=[c for c in node.children if not c.terminal or c.public_verified]
                if not candidates:break
                node=max(candidates,key=lambda c:c.uct(settings['exploration_weight']))
                events.append({'event':'uct_selection','depth':node.depth,'visits':node.visits})
            env.restore(node.checkpoint)
            while not node.terminal and node.depth<settings['depth']:
                if node.children:
                    node=max(node.children,key=lambda c:(c.public_verified,c.prior));env.restore(node.checkpoint)
                else:node=expand(node)
                events.append({'event':'greedy_simulation','depth':node.depth,'prior':node.prior})
            reward=1.0 if node.public_verified else node.prior
            backprop(node,reward);events.append({'event':'backprop','rollout':rollout,'reward':reward})
            if node.prior>best.prior:best=node
            if node.public_verified:
                best=node;submitted=True;reason='public_internal_verification';break
            ref=client.complete(messages(instruction,node.history,
                'Reflect on this unsuccessful or incomplete trajectory. Identify observed failures and concrete alternatives. '
                'Keep under2000 characters; no invented benchmark feedback.'),'lats_reflection')
            reflections.append(clip_bytes(ref,6000));events.append({'event':'reflection','rollout':rollout})
    except BudgetStop as e:reason=str(e)
    finally:
        # Select a concrete tested state, never the arbitrary last visited branch.
        if not submitted:
            evaluated=[n for n in nodes if n.depth>0]
            if evaluated:best=max(evaluated,key=lambda n:n.prior)
        env.restore(best.checkpoint)
        save(env.directory/'lats-search.json',{'events':events,'reflections':reflections,
            'selected_depth':best.depth,'selected_prior':best.prior,'nodes':len(nodes),
            'selected_state_sha256':best.checkpoint['sha256'],'internal_reward_is_official':False})
    return {'stop_reason':reason,'submitted':submitted,'search_nodes':len(nodes),
            'reflections':len(reflections),'branch_diversity':[e['unique'] for e in events if e['event']=='expansion']}

class Taco:
    def __init__(self,client,directory,instruction,cache_path):
        from taco_native.compression import CompressionPlanner,RuleEvolver,FeedbackCollector,RuleCache,DynamicCompressionFilter
        from taco_native.compression.evo_logger import SelfEvoLogger
        from taco_native.output_filter import SafeOutputFilter
        self.client=client;self.instruction=instruction;self.directory=Path(directory)
        self.cache=RuleCache(cache_path);self.cached=self.cache.load('general')
        self.logger=SelfEvoLogger(self.directory)
        self.planner=CompressionPlanner(client,self.logger)
        plan=self.planner.generate_plan(instruction,'general','/app',self.cached)
        client.check_auxiliary()
        self.rules=plan.all_active_rules()+[r.model_copy(deep=True) for r in self.cached if r.rule_id in plan.selected_rule_ids]
        self.filter=SafeOutputFilter();self.feedback=FeedbackCollector(self.logger)
        self.evolver=RuleEvolver(client,self.logger);self.dynamic=DynamicCompressionFilter;self.last_full=None
        for r in self.rules:self.filter.add_filter(self.dynamic(r))
        save(self.directory/'pool-input.json',[r.model_dump() for r in self.cached])

    def process(self,raw,command,episode):
        from taco_native.filter_prompts import get_compress_prompt
        result=self.filter.process(raw,command);out=result.output
        if result.need_llm_compress and not result.is_redundant:
            # Same author compression prompt, explicit budget excerpt if needed.
            prompt=get_compress_prompt(result.llm_compress_type).format(command=command,
                terminal_output=clip_bytes(out,30000),task_instruction=self.instruction[:500])
            text,_=self.client.chat_with_usage(user_content=prompt)
            parsed=self.planner._extract_json(text)
            if parsed.get('is_safe_to_compress') and not parsed.get('has_error') and isinstance(parsed.get('summary'),str):
                out=parsed['summary']
        applied=[n.removeprefix('dynamic_') for n in result.applied_filters if n.startswith('dynamic_')]
        # Author host emits prefixed filter names but models/cache store bare IDs.
        # Explicit namespace mapping ensures complaints freeze the REAL rule.
        self.feedback.record_compression(episode,command,raw,out,applied)
        self.last_full=raw
        signal=self.feedback.detect_uncovered(episode,command,raw,applied)
        if signal:
            r=self.evolver.spawn_new(signal,self.instruction)
            self.client.check_auxiliary()
            if r:self.rules.append(r);self.filter.add_filter(self.dynamic(r))
        save(self.directory/'compressions'/f'{episode:04d}.json',{'command':command,'raw':raw,'compressed':out,
            'applied_rule_ids':applied,'before_chars':len(raw),'after_chars':len(out)})
        return out

    def respond(self,a,episode):
        signal=self.feedback.detect_complaint(episode,json.dumps(a),a.get('compression_feedback',''),
            analysis=a.get('analysis',''),commands=[shlex.join(a.get('argv',[]))])
        if signal:
            for rid in signal.rules_applied:
                old=next((r for r in self.rules if r.rule_id==rid),None)
                if old:
                    new=self.evolver.spawn_replacement(old,signal)
                    self.client.check_auxiliary()
                    if new:self.rules.append(new);self.filter.add_filter(self.dynamic(new))
            return self.last_full
        self.evolver.boost_confidence(self.rules,self.feedback._last_rules_applied)
        return None

    def finish(self):
        self.logger.log_final_state([r.model_dump() for r in self.rules])
        self.cache.save('general',self.rules)
        save(self.directory/'pool-output.json',[r.model_dump() for r in self.rules])

def linear(client,env,instruction,taco=False,cache_path=None):
    history=[];compressor=Taco(client,env.directory/'taco',instruction,cache_path) if taco else None
    episode=0;reason='model_submit';submitted=False
    try:
        while True:
            a=action(client,instruction,history,'Set compression_feedback="need_full_output" if compression hid needed information.' if taco else '')
            if compressor:
                full=compressor.respond(a,episode)
                if full is not None:
                    if history:history[-1]['observation']=clip_bytes(full,24000)
                    # Re-consider action after restoration; no duplicate tool execution.
                    a=action(client,instruction,history,'Previous raw observation restored after compression complaint.')
            if a['action']=='submit':submitted=True;break
            result=env.execute(a);episode+=1;raw=observation(result)
            out=compressor.process(raw,shlex.join(a['argv']),episode) if compressor else raw
            history.append({'action':a,'observation':clip_bytes(out,24000)})
    except BudgetStop as e:reason=str(e)
    finally:
        if compressor:compressor.finish()
    return {'stop_reason':reason,'submitted':submitted,'episodes':episode,'taco_enabled':taco}
