"""TB4 selected tasks ship test dependencies in their original verifier images."""
import contextlib,json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent
@contextlib.contextmanager
def verifier_network(verifier):
 yield
async def prepare_verifier(verifier):
 name=verifier.task.paths.task_dir.name
 seal=json.loads((ROOT/'dependencies/ready.json').read_text())['files']
 p=verifier.task.paths.task_dir/'tests/test.sh';key='official/tasks/'+name+'/tests/test.sh'
 if key not in seal or hashlib.sha256(p.read_bytes()).hexdigest()!=seal[key]:raise RuntimeError('Official verifier drift')
def validate_test_report(verifier):
 p=verifier.trial_paths.verifier_dir/'ctrf.json'
 if not p.is_file():raise RuntimeError('Official tests did not produce a report; score not accepted')
 d=json.loads(p.read_text()).get('results',{});n=d.get('summary',{}).get('tests');tests=d.get('tests',[])
 if type(n) is not int or n<=0 or len(tests)!=n:raise RuntimeError('No complete official test report')
 reward=verifier.trial_paths.verifier_dir/'reward.txt'
 if reward.exists() and reward.read_text().strip()=='1' and any(t.get('status')=='failed' for t in tests):raise RuntimeError('Reward contradicts tests')
