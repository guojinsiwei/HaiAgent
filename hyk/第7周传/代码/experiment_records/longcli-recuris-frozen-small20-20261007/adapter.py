"""No oracle, no TTA: handoff W/rho/C on the SAME stateless CLI budget."""
from dataclasses import asdict
import json
from pathlib import Path
import sys
import time
from common import ROOT,save
from client import BudgetStop,ModelFault,envelope_bytes,clip_bytes

sys.path.insert(0,str(ROOT/'recuris/src'))
from recuris.audit import JsonlLogger
from recuris.client import ModelReply,ModelClientError
from recuris.engine import RecurisRunner,RecurisConfig,_Stopped
from recuris.memory import load_memory,memory_digest
from recuris.prompts import ACTOR
from recuris.working import verifier_digest

ENVIRONMENT=('Runtime contract: /app is the working directory. Read INSTRUCTION.md. '
    'Each command is a complete bash script in a FRESH shell; cwd and shell variables do not persist. '
    'Use cd directory && command inside each script. No interactive programs or persistent background services. '
    'Network is disabled, hidden tests/scores and credentials are unavailable. '
    'A command waits for completion and is stopped after at most300 seconds; descendants are stopped too. '
    'Duration is a compatibility field, not permission for longer execution. '
    'No public check is an official score. Submit exactly once. No test-result-driven retry or memory evolution.')
STATELESS_ACTOR='\n'.join(
    '- execute: keystrokes is a complete shell script, NOT interactive keystrokes; it runs in a fresh bash at /app. Empty input and C-c do not control a background job. goal_id must be empty. Prior done goals reopen after nonempty input.'
    if line.startswith('- execute:') else
    'duration is retained for schema compatibility; each script runs until completion or the shared300s command limit. There are no outstanding commands to poll.'
    if line.startswith('duration is ') else line.replace('persistent terminal','stateless command environment').replace('Ensure the foreground shell is ready.','The public check starts in a new shell at /app.')
    for line in ACTOR.splitlines())+'\n'+ENVIRONMENT

class SharedClientBridge:
    def __init__(self,backend):self.backend=backend
    def complete(self,messages,*,purpose,deadline_monotonic=None):
        if deadline_monotonic is not None and time.monotonic()>=deadline_monotonic:raise _Stopped('wall_seconds')
        before=dict(self.backend.usage)
        try:content=self.backend.complete(messages,'recuris_'+purpose)
        except BudgetStop as exc:raise _Stopped(str(exc)) from None
        except ModelFault as exc:raise ModelClientError(str(exc)) from None
        return ModelReply(content=content,input_tokens=self.backend.usage['prompt_tokens']-before['prompt_tokens'],
                          output_tokens=self.backend.usage['completion_tokens']-before['completion_tokens'],finish_reason='stop')

class CommandTerminal:
    def __init__(self,env):self.env=env;self.last_result=None
    def observe(self):return ENVIRONMENT
    def execute(self,keys,duration):
        if not isinstance(keys,str):raise TypeError('invalid_shell_script')
        if not keys.strip() or keys=='C-c':
            self.last_result=None
            return 'No running command: each previous script has completed or been stopped. No polling/interactive shell.'
        try:self.last_result=self.env.execute({'argv':['bash','-c',keys],'cwd':'.','timeout_seconds':300})
        except BudgetStop as exc:raise _Stopped(str(exc)) from None
        r=self.last_result
        return 'Exit code: '+str(r['exit_code'])+'\nSTDOUT:\n'+r['stdout']+'\nSTDERR:\n'+r['stderr']

class MatchedRunner(RecurisRunner):
    @staticmethod
    def _size(messages):return envelope_bytes(messages)
    def _actor_messages(self,instruction,initial,history,active_skills):
        result=super()._actor_messages(instruction,initial,history,active_skills)
        result[0]['content']=STATELESS_ACTOR
        # Larger explicit runtime prompt can require one more whole-pair removal.
        while self._size(result)>45000 and len(result)>2:del result[2:4]
        if len(result)<2+len(history):
            result[1]['content']+='\n[Explicit UTF8 budget projection: older full pairs omitted; full trace retained.]'
        return result
    def _visible_receipt(self,receipt):
        value=dict(receipt);full=value.get('output','')
        value['output']=clip_bytes(full,24000)
        value['output_truncated']=len(full.encode())>24000
        return value
    def _verify(self,terminal,goal,duration):
        # Receipts come from the shared process driver, never from model text.
        # Timed-out commands have genuinely terminated with124 and cannot prove done.
        output=self._terminal(terminal,goal['verification']['command'],300)
        r=terminal.last_result
        if not isinstance(r,dict) or type(r.get('exit_code')) is not int:raise RuntimeError('missing_actual_exit_receipt')
        return {'kind':'verification','goal_id':goal['id'],
            'verification_digest':verifier_digest(goal['verification']),'revision':self._revision,
            'output':output,'completed':True,'exit_code':r['exit_code'],'synthetic':False,
            'timed_out':r['timed_out'],'output_truncated':r.get('output_truncated',False)}

def run_recuris(client,env,instruction):
    memory=load_memory(ROOT/'terminal_seed.json');initial_digest=memory_digest(memory)
    config=RecurisConfig(max_steps=800,max_tool_calls=600,max_model_calls=800,
        max_total_seconds=max(0.01,client.deadline-time.monotonic()),max_context_chars=48000,
        max_observation_chars=24000,max_command_duration=300,max_verify_seconds=300,
        max_parse_attempts=2,max_consecutive_tool_errors=10,history_turns=12)
    engine=MatchedRunner(SharedClientBridge(client),config,memory,
                         JsonlLogger(env.directory/'recuris-trace',secrets=(client.key,)))
    result=engine.run(instruction+'\n'+ENVIRONMENT,CommandTerminal(env))
    assert memory_digest(engine.memory)==initial_digest
    save(env.directory/'recuris-result.json',asdict(result))
    if result.error is not None:raise ModelFault('recuris_'+result.stop_reason)
    stop=result.stop_reason
    if stop=='max_context_chars_reached':stop='input_bytes'
    return {'stop_reason':stop,'submitted':result.stop_reason in ('task_complete','actor_stopped_incomplete'),
        'steps':result.steps,'working_goals':len(result.working_state),'memory_digest':initial_digest,
        'engine_model_calls':result.model_calls,'engine_terminal_calls':result.tool_calls,
        'official_feedback_seen':False,'meta_calls':0,'attempts':1,'mode':'frozen'}
