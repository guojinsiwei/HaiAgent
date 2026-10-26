"""Frozen KZ2.0 algorithm, in-place official TB4 workspace, no DSH agent loop."""
import json,os,sys,time,uuid,shutil
from pathlib import Path
HERE=Path(__file__).resolve().parent;OLD=HERE/'legacy'
sys.path[:0]=[str(OLD),str(OLD/'sources/bestfgs-project/src'),str(OLD/'compatibility/src')]
from bestfgs.lean_environment import LiveWorkspace
from bestfgs.environment import _copy_workspace,_tree_fingerprint
from bestfgs.error_routing import RoutedTaskRunner,RoutingPolicy
from bestfgs.lean_protocol import LeanConfig
from bestfgs.models import TaskSpec
from bestfgs.retrac_adapter import RetracModelConfig
from shared_wire import SharedJSONWire
from audit import Audit,JSONClientAudit
from budget_adapter import CheckedTransport,install_context_meter
from repair_runtime import install_dh
from anthropic_bridge import request
from native_repair import RepairRunner

def save(p,v):
    t=p.with_suffix('.tmp');t.write_text(json.dumps(v,ensure_ascii=False));t.replace(p)
class InPlace(LiveWorkspace):
    def __init__(self,workspace,root):
        self.workspace=Path(workspace).resolve();self.root=root;root.mkdir(parents=True,exist_ok=False)
        self.seed=self.workspace;self.checkpoints={};self.credential_variables={'TAOTOKEN_API_KEY','OPENAI_API_KEY','DEEPSEEK_API_KEY'}
    def restore(self,record):
        raise ValueError('Workspace restore is frozen; no files were moved')
class Observed(RepairRunner):
    def _emit(self,event,**fields):
        super()._emit(event,**fields)
        save(self.live/'progress.json',dict(time=time.time(),event=event,tools=self.counts.get('tool_calls',0),requests=self.counts.get('model_requests',0)))
class WireAudit(Audit):
    def __init__(self,path,**kwargs):
        super().__init__(path,**kwargs);self.wire_requests=0;self.statuses={}
    def emit(self,event,**fields):
        super().emit(event,**fields)
        if event=='wire_request':self.wire_requests+=1
        if event=='wire_response':
            status='200' if fields.get('kind')=='ok' else str(fields.get('status') or fields.get('kind'))
            self.statuses[status]=self.statuses.get(status,0)+1
        if event in ('wire_request','wire_response','wire_rejected'):
            save(self.path.parent/'wire-state.json',dict(requests=self.wire_requests,http_status_counts=self.statuses,time=time.time()))
def main():
    bundle=json.load(sys.stdin);key=bundle.pop('key');live=Path('/logs/agent/live');live.mkdir(parents=True,exist_ok=True)
    install_dh();install_context_meter();deadline=time.monotonic()+10800
    audit=WireAudit(live/'model-audit.jsonl',secrets=(key,));clients={}
    for role in ('action','advisor','monitor','critic'):
        cfg=RetracModelConfig(provider='deepseek',model_name=os.environ.get('CAMPAIGN_MODEL','deepseek-flash'),api_key=key,base_url=os.environ.get('MODEL_MESSAGES_ENDPOINT','https://api.taotoken.net/token/v1/messages').removesuffix('/messages'),temperature=0,
            timeout_seconds=90,max_wall_time_seconds=180,request_attempts=1 if role=='monitor' else 2,parse_attempts=1,stream_response=False,thinking_enabled=False,max_tokens=32768)
        wire=SharedJSONWire(cfg,audit,role,transport=CheckedTransport(audit,transport=request))
        clients[role]=JSONClientAudit(wire,audit,role,deadline)
    # Recovery uses the shared task deadline, not a three-format-error cutoff.
    cfg=LeanConfig(max_turns=sys.maxsize,max_tools=sys.maxsize,wall_seconds=10800,command_seconds=600,
        semantic_monitor=True,auto_memory=True,memory_reliability=True,monitor_reliability=True,outcome_reliability=True,
        stagnation_control=False,route_search=False,contrastive_mode='orthogonal',contrastive_predictions=False,
        contrastive_threshold=.8,context_chars=3737856,subgoals_enabled=True,
        max_consecutive_errors=sys.maxsize)
    env=InPlace(Path.cwd(),live/'workspace-state')
    engine=Observed(env,clients['action'],clients['advisor'],cfg,live/'trace',secrets=(key,),monitor_client=clients['monitor'],
       routing=RoutingPolicy(local_correction=True,reconnaissance=True,critic=True,backtracking=False,critic_limit=sys.maxsize),critic_client=clients['critic'])
    engine.live=live
    # Retain the original public task convention WITHOUT replacing an existing file.
    instruction=live/'INSTRUCTION.md'
    if not instruction.exists():instruction.write_text(bundle['instruction'])
    result=engine.run(TaskSpec(bundle['task'],bundle['instruction'],constraints=(
        'Use the public requirements and current official workspace; hidden grading occurs after delivery.',
        'Each command uses a fresh shell. Workspace-file rollback is not process/network rollback.',
        'Public verification and Critic acceptance are not official task success.')))
    save(live/'result.json',result)
    save(live/'usage.json',{role:c.usage_summary() for role,c in clients.items()})
    engineering=result.get('stop_reason') in {'infrastructure_error','delivery_error','credential_or_balance_error','model_error','model_or_protocol_error_limit'}
    save(live/'run-status.json',dict(engineering_failure=engineering,
        submitted=bool(result.get('submitted')),stop_reason=result.get('stop_reason'),
        unregistered_plan=bool(engine.subgoals and engine.subgoals.rejected_plan)))
    if engineering:raise SystemExit(2)
if __name__=='__main__':
    try:main()
    except Exception as error:
        # Do not serialize exception text, requests, or credentials.
        import traceback
        live=Path('/logs/agent/live')
        record=dict(engineering_failure=True,error_type=type(error).__name__,
            frames=[dict(file=Path(f.filename).name,line=f.lineno,function=f.name)
                    for f in traceback.extract_tb(error.__traceback__)[-8:]])
        try:save(live/'run-status.json',record)
        except OSError:pass
        print(json.dumps(record),file=sys.stderr,flush=True)
        raise SystemExit(2)
