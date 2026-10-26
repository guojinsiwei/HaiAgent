"""Three frozen algorithms, one strict wire and isolated CLI executor."""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import time
from common import ROOT, save, export_tree
from environment import NativeEnvironment, SandboxExecutor
from audit import Audit, JSONClientAudit, verify
from shared_wire import SharedJSONWire, RawJSONClient
from bestfgs.lean_protocol import LeanConfig
from bestfgs.lean_runtime import LeanTaskRunner
from bestfgs.models import TaskSpec
from bestfgs.retrac_adapter import RetracModelConfig
from haiagent.protocol import Config, Task
from haiagent.runtime import run
from haiagent.demo import ScriptedClient

CONSTRAINTS=(
 'Only public files are available. Hidden tests run once after the artifact is frozen; no hidden-test feedback during solving.',
 'Work in /app; temporary files may go in /tmp. Only /app files are checkpointed and delivered; /tmp is not preserved by restoration or grading. System files are protected. Task command network is disabled.',
 'Each command has a fresh process namespace; background services do not persist. Python and C/C++ toolchains are preinstalled.',
 'Decide when to submit. A submission or exit code zero does not imply task success.')

class ScriptedJSON:
    def __init__(self,values):self.values=iter(values)
    def complete_json(self,**kwargs):return next(self.values)
    def usage_summary(self):return dict(model_calls=0,api_requests=0,prompt_tokens=0,completion_tokens=0)

def lean_config(protocol,method):
    kwargs=dict(max_turns=protocol['max_turns'],max_tools=protocol['max_tools'],
                wall_seconds=protocol['wall_seconds'],command_seconds=protocol['command_seconds'],
                semantic_monitor=True,auto_memory=True,memory_reliability=True,
                monitor_reliability=True,outcome_reliability=True,stagnation_control=True)
    if method=='orthogonal-v8':
        kwargs.update(memory_enabled=True,memory_decision=True,stagnation_control=False,
                      route_search=False,contrastive_mode='orthogonal',contrastive_threshold=.8)
    return LeanConfig(**kwargs)

def run_one(row,key='',fixture=False):
    protocol=json.loads((ROOT/'protocol.json').read_text())
    base=ROOT/('fixtures' if fixture else 'runs')/row['job'];base.mkdir(parents=True,exist_ok=False)
    image=ROOT/'roots'/row['job'];assert (image/'app/INSTRUCTION.md').is_file()
    audit=Audit(base/'model-audit.jsonl',secrets=(key,));start=time.monotonic();deadline=start+row['wall_seconds']
    audit.emit('trial_start',method=row['method'],task=row['task'],fixture=fixture,
               budgets=dict(tools=protocol['max_tools'],turns=protocol['max_turns'],wall=row['wall_seconds']))
    decisions=[dict(action='run',argv=['python3','-c',
      'from pathlib import Path; assert Path("INSTRUCTION.md").is_file(); print("fixture-ok")'],purpose='fixture'),
      dict(action='submit',summary='Offline infrastructure check, not a solution')]
    raw_config=Config(method='raw',response_protocol='json',max_turns=protocol['max_turns'],
        max_tools=protocol['max_tools'],wall_seconds=row['wall_seconds'],command_seconds=protocol['command_seconds'],
        request_seconds=90,api_attempts=2,output_bytes=24000,prompt_bytes=48000,max_tokens=4096,temperature=0)
    def model_config(role):
        return RetracModelConfig(provider='deepseek',model_name=protocol['model'],
            base_url='https://api.deepseek.com',api_key=key,temperature=0,timeout_seconds=90,
            max_wall_time_seconds=180,request_attempts=1 if role=='monitor' else 2,parse_attempts=1,stream_response=False,
            thinking_enabled=False,max_tokens=4096 if role=='action' else 1536)
    if row['method']=='raw':
        client=ScriptedClient(decisions) if fixture else RawJSONClient(SharedJSONWire(model_config('action'),audit))
        result=run(Task(row['task'],row['instruction'],image/'app',delivery='terminal',
            environment_revision=row['image_id'],constraints=CONSTRAINTS),raw_config,client,base/'trace',
            executor=SandboxExecutor(image),secrets=(key,))
        result['model_usage']={'action':dict(model_calls=0,api_requests=0) if fixture else client.usage}
        result['mechanism_utilization']=dict(memory=False,advisor=False,monitor=False,branch_restore=False)
    else:
        clients={role:JSONClientAudit(ScriptedJSON(decisions if role=='action' else []) if fixture
            else SharedJSONWire(model_config(role),audit,role),audit,role,None if fixture else deadline)
            for role in ('action','advisor','monitor')}
        cfg=lean_config(dict(protocol,wall_seconds=row['wall_seconds']),row['method'])
        env=NativeEnvironment(image,base/'checkpoints')
        result=LeanTaskRunner(env,clients['action'],clients['advisor'],cfg,base/'trace',
            secrets=(key,),monitor_client=clients['monitor']).run(TaskSpec(row['task'],row['instruction'],constraints=CONSTRAINTS))
    audit.emit('trial_end',result=result)
    artifact=export_tree(image/'app',base/'source.tar.gz',source_only=True)
    summary=dict(job=row['job'],task=row['task'],method=row['method'],worker=row['worker'],
        submitted=result.get('submitted',False),stop_reason=result.get('stop_reason'),
        interaction_rounds=result.get('interaction_rounds'),tool_calls=result.get('tool_calls'),
        elapsed_seconds=time.monotonic()-start,artifact=artifact,official_success=None,
        mechanism_utilization=result.get('mechanism_utilization'),model_usage=result.get('model_usage'),
        audit=verify(base/'model-audit.jsonl'),fixture=fixture)
    save(base/'result.json',result);save(base/'summary.json',summary);return summary

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--row',required=True);parser.add_argument('--credential',required=True)
    args=parser.parse_args()
    print(json.dumps(run_one(json.loads(Path(args.row).read_text()),Path(args.credential).read_text().strip())),flush=True)
