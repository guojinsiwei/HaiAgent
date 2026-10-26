"""Frozen planner/solver graph v3 on isolated public-only LongCLI roots."""
import argparse
import json
import os
from pathlib import Path
import time
from common import ROOT,save,export_tree
from environment import NativeEnvironment
from audit import Audit,JSONClientAudit,verify
from shared_wire import SharedJSONWire
from bestfgs.graph_planner import PlannerSolverGraphRunner,PlannerLimits
from bestfgs.graph_search import GraphLimits
from bestfgs.lean_protocol import LeanConfig
from bestfgs.models import TaskSpec
from bestfgs.retrac_adapter import RetracModelConfig

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
    if method!='planner-v3':raise ValueError('Unknown frozen method')
    return LeanConfig(max_turns=protocol['max_turns'],max_tools=protocol['max_tools'],
        wall_seconds=protocol['wall_seconds'],command_seconds=protocol['command_seconds'],
        semantic_monitor=True,auto_memory=True,memory_reliability=True,monitor_reliability=True,
        outcome_reliability=True,memory_enabled=True,memory_decision=True,memory_injection=True,
        stagnation_control=False,route_search=False,contrastive_mode='off',
        context_chars=protocol['context_limit'],max_advisor_calls=protocol['role_limits']['advisor'],
        max_monitor_calls=protocol['role_limits']['monitor'])

def fixture_responses():
    def command(code):return dict(action='run',argv=['python3','-c',code],purpose='offline graph fixture')
    left=command('from pathlib import Path; Path(".graph-v3-fixture").write_text("A"); print("fixture-A"); raise SystemExit(1)')
    right=command('from pathlib import Path; assert not Path(".graph-v3-fixture").exists(); assert Path("INSTRUCTION.md").is_file(); Path(".graph-v3-fixture").write_text("B"); print("fixture-B")')
    actors=[dict(candidates=[dict(kind='probe',hypothesis='Try isolated fixture branch',
        expected_evidence='Observe fixture output',action=a) for a in (left,right)]),
        command('from pathlib import Path; assert Path(".graph-v3-fixture").read_text()=="B"; Path(".graph-v3-fixture").unlink(); print("fixture-clean")'),
        dict(action='submit',summary='Offline infrastructure check only, unmodified public starter')]
    plans=[dict(selection=dict(kind=kind,id=identifier),reason='Inspect isolated fixture behavior',
        subgoal='Validate real parent restoration',success_observation='Fixture branch B sees no branch A file')
        for kind,identifier in (('expand','N0'),('edge','G1'),('edge','G2'))]
    return dict(action=actors,planner=plans,advisor=[],monitor=[])

def model_config(protocol,key,role):
    return RetracModelConfig(provider='deepseek',model_name=protocol['model'],
        base_url=protocol['endpoint'],api_key=key,temperature=0,thinking_enabled=False,
        timeout_seconds=90 if role=='action' else 30 if role=='monitor' else 45,
        max_wall_time_seconds=180 if role=='action' else 45 if role=='monitor' else 60,
        request_attempts=protocol['role_wire_attempts'][role],parse_attempts=1,stream_response=False,
        max_tokens=protocol['role_output_tokens'][role])

def run_one(row,key='',fixture=False):
    protocol=json.loads((ROOT/'protocol.json').read_text())
    base=ROOT/('fixtures' if fixture else 'runs')/row['job'];base.mkdir(parents=True,exist_ok=False)
    image=ROOT/'roots'/row['job'];assert (image/'app/INSTRUCTION.md').is_file()
    audit=Audit(base/'model-audit.jsonl',secrets=(key,));start=time.monotonic();deadline=start+row['wall_seconds']
    audit.emit('trial_start',method=row['method'],task=row['task'],fixture=fixture,
        algorithm='planner-solver-graph-v3',cpu_affinity=sorted(os.sched_getaffinity(0)),
        budgets=dict(tools=protocol['max_tools'],turns=protocol['max_turns'],wall=row['wall_seconds']),
        graph_limits=protocol['graph_limits'],planner_limits=protocol['planner_limits'])
    responses=fixture_responses() if fixture else None
    clients={role:JSONClientAudit(ScriptedJSON(responses[role]) if fixture else
        SharedJSONWire(model_config(protocol,key,role),audit,role),audit,role,None if fixture else deadline)
        for role in ('action','planner','advisor','monitor')}
    cfg=lean_config(dict(protocol,wall_seconds=row['wall_seconds']),row['method'])
    limits=dict(protocol['graph_limits'])
    if fixture:limits['max_expansions_per_node']=1
    env=NativeEnvironment(image,base/'checkpoints')
    result=PlannerSolverGraphRunner(env,clients['action'],clients['advisor'],cfg,base/'trace',
        secrets=(key,),monitor_client=clients['monitor'],planner_client=clients['planner'],
        graph_limits=GraphLimits(**limits),planner_limits=PlannerLimits(**protocol['planner_limits'])).run(
            TaskSpec(row['task'],row['instruction'],constraints=CONSTRAINTS))
    audit.emit('trial_end',result=result)
    artifact=export_tree(image/'app',base/'source.tar.gz',source_only=True)
    summary=dict(job=row['job'],task=row['task'],method=row['method'],worker=row['worker'],
        submitted=result['submitted'],stop_reason=result['stop_reason'],error_type=result['error_type'],
        interaction_rounds=result['interaction_rounds'],tool_calls=result['tool_calls'],
        planner_rounds=result['planner_rounds'],graph_diagnostics=result['graph_diagnostics'],
        elapsed_seconds=time.monotonic()-start,artifact=artifact,official_success=None,
        mechanism_utilization=result['mechanism_utilization'],model_usage=result['model_usage'],
        audit=verify(base/'model-audit.jsonl'),fixture=fixture)
    save(base/'result.json',result);save(base/'summary.json',summary)
    return summary

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--row',required=True);p.add_argument('--credential',required=True)
    args=p.parse_args();row=json.loads(Path(args.row).read_text())
    if 'cpu_affinity' in row:
        if not set(row['cpu_affinity']).issubset(os.sched_getaffinity(0)):raise RuntimeError('Assigned task CPUs unavailable')
        os.sched_setaffinity(0,row['cpu_affinity'])
    print(json.dumps(run_one(row,Path(args.credential).read_text().strip())),flush=True)
