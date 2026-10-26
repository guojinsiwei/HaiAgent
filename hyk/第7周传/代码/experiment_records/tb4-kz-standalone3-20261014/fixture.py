"""Run original KZ loop with scripted replies inside disposable task container."""
import json,tempfile
from pathlib import Path
import solve
class Scripted:
    def __init__(self,values):self.values=iter(values)
    def complete_json(self,**kwargs):return next(self.values)
    def usage_summary(self):return dict(model_calls=0,api_requests=0)
def main():
 with tempfile.TemporaryDirectory(prefix='kz-offline-') as folder:
    root=Path(folder);workspace=root/'workspace';workspace.mkdir();(workspace/'INSTRUCTION.md').write_text('Print OFFLINE_OK and submit.')
    env=solve.InPlace(workspace,root/'state')
    actor=Scripted([dict(action='run',argv=['python3','-c','print("OFFLINE_OK")']),dict(action='submit',summary='fixture')])
    critic=Scripted([dict(decision='accept',requirements=['fixture'],gaps=[],checks=[dict(argv=['python3','-c','print("CHECK_OK")'],stdout_contains=['CHECK_OK'])]),dict(decision='accept',requirements=['fixture'],gaps=[],checks=[])])
    cfg=solve.LeanConfig(max_turns=20,max_tools=10,wall_seconds=120,context_chars=48000,outcome_reliability=True,subgoals_enabled=True)
    engine=solve.RoutedTaskRunner(env,actor,Scripted([]),cfg,root/'trace',critic_client=critic,routing=solve.RoutingPolicy(critic=True,backtracking=False))
    result=engine.run(solve.TaskSpec('fixture','Print OFFLINE_OK and submit.'))
    assert result['submitted'],result.get('stop_reason')
    assert result['tool_calls']==2,result['tool_calls']
    print(json.dumps(dict(passed=True,real_shell=True,original_loop=True,critic_checks=1,api_calls=0)))
if __name__=='__main__':main()
