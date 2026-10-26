import json,subprocess,inspect
from pathlib import Path
B=Path('/mnt/sdb/home/lizh639');S=B/'tb2-three-arm50-boost6-20261018'
h=json.loads((S/'health.json').read_text())
for task in dict.fromkeys(r['task'] for r in h['rows']):
 p=S/'dependencies/official/tasks'/task
 print('\nTASK',task,'\n', (p/'tests/test.sh').read_text(), '\nMANIFEST', (p/'task.toml').read_text())
for r in h['rows']:
 p=Path(r['result']['trial']);result=json.loads((p/'result.json').read_text())
 print('FAILURE',r['arm'],r['task'],json.dumps(result.get('exception_info',{}).get('exception_message')))
 log=p/'verifier/test-stdout.txt'
 if log.exists():print('TAIL',log.read_text(errors='replace')[-2200:])
ids=subprocess.check_output(['docker','ps','-aq','--filter','label=com.docker.compose.project=torch-pipeline-parallelism__ksib3ke'],text=True).split()
for cid in ids:
 c=json.loads(subprocess.check_output(['docker','inspect',cid]))[0]
 print('SAVED_CONTAINER',json.dumps({k:c[k] for k in ('Id','Name','State','Mounts')},default=str))
from harbor.verifier.verifier import Verifier
print('VERIFIER_SOURCE',inspect.getsource(Verifier))
