"""Frozen v6.1 versus plain RAW, same private command environment."""
import argparse
from dataclasses import replace
from functools import partial
import json
from pathlib import Path
import time
import urllib.error

from common import ROOT, save, export_tree
from environment import NativeEnvironment, SandboxExecutor
from audit import Audit, JSONClientAudit, HAIClientAudit, verify
from net_transport import request
from bestfgs.lean_protocol import LeanConfig
from bestfgs.lean_runtime import LeanTaskRunner
from bestfgs.monitor_config import monitor_config
from bestfgs.models import TaskSpec
from bestfgs.retrac_adapter import RetracModelConfig, OpenAICompatibleJSONClient
from haiagent.protocol import Config, Task
from haiagent.model import APIClient
from haiagent.runtime import run
from haiagent.demo import ScriptedClient

CONSTRAINTS = (
 'Only public files are available. Hidden tests run once after the artifact is frozen; no hidden-test feedback during solving.',
 'Work in /app; temporary files may go in /tmp. Only /app files are checkpointed and delivered; /tmp is not preserved by restoration or grading. System files are protected. Task command network is disabled.',
 'Each command has a fresh process namespace; background services do not persist. Python and C/C++ toolchains are preinstalled.',
 'Decide when to submit. A submission or exit code zero does not imply task success.')

def transport(endpoint, payload, key, seconds, recorder=None):
    payload = dict(payload, thinking={'type':'disabled'})
    return request(endpoint, payload, key, seconds,recorder=recorder)

class JSONTransport(OpenAICompatibleJSONClient):
    def __init__(self, config, audit=None, role='action'):
        super().__init__(config)
        self.wire_audit,self.wire_role=audit,role

    def _request_bytes(self, *, endpoint, encoded, headers):
        if self.wire_audit: self.wire_audit.emit('wire_request',role=self.wire_role,payload=json.loads(encoded))
        kind, body = transport(endpoint, json.loads(encoded), self.config.api_key,
                               min(self.config.timeout_seconds,self.config.max_wall_time_seconds),recorder=self.wire_audit)
        if self.wire_audit:
            envelope=None
            if kind=='ok':
                try: envelope=json.loads(body)
                except ValueError: envelope=dict(invalid_json=True,content_preview=body.decode(errors='replace')[:2000])
            self.wire_audit.emit('wire_response',role=self.wire_role,kind=kind,
                envelope=envelope,status=body if kind!='ok' else None)
        if kind == 'ok':
            return body
        if kind == 'http':
            raise urllib.error.HTTPError(endpoint, body, 'provider_'+str(body), {}, None)
        raise urllib.error.URLError('bounded_transport_'+kind)

class RawPathClient(HAIClientAudit):
    def __init__(self, inner, audit):
        super().__init__(inner,audit)
        self.usage=dict(model_calls=0,api_requests=0,api_responses=0,prompt_tokens=0,
                        completion_tokens=0,total_tokens=0,usage_reports=0,returned_models=[],
                        cached_prompt_tokens=0,cache_miss_prompt_tokens=0)

    def complete(self, messages, deadline, recorder):
        messages = json.loads(json.dumps(messages))
        payload = json.loads(messages[1]['content'])
        payload['workspace'] = '/app'
        messages[1]['content'] = json.dumps(payload,ensure_ascii=False)
        owner=self
        class Recording:
            def emit(self,event,**fields):
                recorder.emit(event,**fields)
                if event in ('api_start','api_end'):
                    owner.audit.emit(event,role='action',**fields)
                if event=='api_start': owner.usage['api_requests']+=1
                if event=='api_end' and fields.get('status')=='response':
                    owner.usage['api_responses']+=1
                    usage=fields.get('usage')
                    if isinstance(usage,dict):
                        owner.usage['usage_reports']+=1
                        for name in ('prompt_tokens','completion_tokens','total_tokens'):
                            if type(usage.get(name)) is int: owner.usage[name]+=usage[name]
                        for target,source in (('cached_prompt_tokens','prompt_cache_hit_tokens'),
                                              ('cache_miss_prompt_tokens','prompt_cache_miss_tokens')):
                            if type(usage.get(source)) is int: owner.usage[target]+=usage[source]
                    model=fields.get('returned_model')
                    if model and model not in owner.usage['returned_models']: owner.usage['returned_models'].append(model)
        if isinstance(self.inner,APIClient): self.usage['model_calls']+=1
        return super().complete(messages,deadline,Recording())

class ScriptedJSON:
    def __init__(self, values): self.values=iter(values)
    def complete_json(self, **kwargs): return next(self.values)
    def usage_summary(self): return {'model_calls':0,'api_requests':0,'prompt_tokens':0,'completion_tokens':0}

def run_one(row, key='', fixture=False):
    protocol=json.loads((ROOT/'protocol.json').read_text())
    base=ROOT/('fixtures' if fixture else 'runs')/row['job']
    base.mkdir(parents=True,exist_ok=False)
    image=ROOT/'roots'/row['job']
    assert (image/'app/INSTRUCTION.md').is_file()
    # Use the actual upstream task.yaml entry point. The complete specification
    # remains a public file; duplicating it in protected context breaks v6 budgets.
    goal=row['instruction']
    audit=Audit(base/'model-audit.jsonl',secrets=(key,))
    started=time.monotonic()
    deadline=started+row['wall_seconds']
    raw_config=Config(method='raw',response_protocol='json',max_turns=protocol['max_turns'],
        max_tools=protocol['max_tools'],wall_seconds=row['wall_seconds'],
        command_seconds=protocol['command_seconds'],request_seconds=90,api_attempts=2,
        output_bytes=24000,prompt_bytes=48000,max_tokens=4096,temperature=0)
    config=LeanConfig(max_turns=protocol['max_turns'],max_tools=protocol['max_tools'],
        wall_seconds=row['wall_seconds'],command_seconds=protocol['command_seconds'],
        semantic_monitor=True,auto_memory=True,memory_reliability=True,
        monitor_reliability=True,outcome_reliability=True,stagnation_control=True)
    decisions=[dict(action='run',argv=['python3','-c',
        'from pathlib import Path; assert Path("INSTRUCTION.md").is_file(); print("fixture-ok")'],purpose='fixture'),
        dict(action='submit',summary='Offline infrastructure check; not a task solution')]
    audit.emit('trial_start',method=row['method'],task=row['task'],fixture=fixture,
               budgets=dict(tools=protocol['max_tools'],turns=protocol['max_turns'],wall=row['wall_seconds']))
    if row['method']=='raw':
        inner=ScriptedClient(decisions) if fixture else APIClient('https://api.deepseek.com',
            protocol['model'],key,raw_config,transport=partial(transport,recorder=audit))
        client=RawPathClient(inner,audit)
        result=run(Task(row['task'],goal,image/'app',delivery='terminal',
            environment_revision=row['image_id'],constraints=CONSTRAINTS),raw_config,
            client,base/'trace',executor=SandboxExecutor(image),secrets=(key,))
        result['model_usage']={'action':client.usage}
        result['mechanism_utilization']=dict(memory=False,advisor=False,monitor=False,branch_restore=False)
    else:
        clients={}
        for role in ('action','advisor','monitor'):
            model_config=None if fixture else RetracModelConfig(provider='deepseek',model_name=protocol['model'],
                    base_url='https://api.deepseek.com',api_key=key,temperature=0,
                    timeout_seconds=90,max_wall_time_seconds=180,request_attempts=2,
                    parse_attempts=1,stream_response=False,thinking_enabled=False,max_tokens=4096)
            if not fixture and role=='advisor': model_config=replace(model_config,max_tokens=1536)
            if not fixture and role=='monitor': model_config=monitor_config(model_config)
            inner=ScriptedJSON(decisions if role=='action' else []) if fixture else JSONTransport(model_config,audit,role)
            clients[role]=JSONClientAudit(inner,audit,role,None if fixture else deadline)
        environment=NativeEnvironment(image,base/'checkpoints')
        result=LeanTaskRunner(environment,clients['action'],clients['advisor'],config,
            base/'trace',secrets=(key,),monitor_client=clients['monitor']).run(
                TaskSpec(row['task'],goal,constraints=CONSTRAINTS))
    audit.emit('trial_end',result=result)
    artifact=export_tree(image/'app',base/'source.tar.gz',source_only=True)
    summary=dict(job=row['job'],task=row['task'],method=row['method'],worker=row['worker'],
        submitted=result.get('submitted',False),stop_reason=result.get('stop_reason'),
        interaction_rounds=result.get('interaction_rounds'),tool_calls=result.get('tool_calls'),
        elapsed_seconds=time.monotonic()-started,artifact=artifact,official_success=None,
        mechanism_utilization=result.get('mechanism_utilization'),model_usage=result.get('model_usage'),
        audit=verify(base/'model-audit.jsonl'),fixture=fixture)
    save(base/'result.json',result)
    save(base/'summary.json',summary)
    return summary

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--row',required=True)
    parser.add_argument('--credential',required=True)
    args=parser.parse_args()
    print(json.dumps(run_one(json.loads(Path(args.row).read_text()),
                             Path(args.credential).read_text().strip())),flush=True)
