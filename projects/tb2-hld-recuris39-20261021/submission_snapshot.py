"""Keep each paid solver filesystem available for scoring-only recovery."""
import asyncio,json,os
from storage import atomic_json
async def snapshot(trial):
 if not (os.environ.get('CAMPAIGN_BUDGET_REQUIRED') or os.environ.get('SCORE_SNAPSHOT_ACCEPTANCE')):return
 env=trial.agent_environment
 # Separate verification deliberately stops main before collecting sidecars.
 result=await env._run_docker_compose_command(['ps','-a','-q','main'],check=True,timeout_sec=30)
 ids=(result.stdout or '').split()
 if len(ids)!=1:raise RuntimeError('Expected one running or stopped main container for snapshot')
 name='kz-score-recovery:'+os.environ['PAIRED_ATTEMPT_ID']
 p=await asyncio.create_subprocess_exec('docker','commit',ids[0],name,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
 out,err=await p.communicate()
 if p.returncode:raise RuntimeError('Solver filesystem snapshot failed')
 atomic_json(trial.paths.trial_dir/'submission-snapshot.json',dict(image_id=out.decode().strip(),tag=name,container_id=ids[0],attempt_id=os.environ['PAIRED_ATTEMPT_ID'],before_verifier=True))
