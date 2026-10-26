import json,subprocess,tarfile,inspect
from pathlib import Path
B=Path('/mnt/sdb/home/lizh639');S=B/'tb2-three-arm50-boost6-20261018'
with tarfile.open(S/'verifier-deps.tar.gz') as t:print('ARCHIVE',t.getnames()[:35])
for task in ['sam-cell-seg','mteb-leaderboard','largest-eigenval','hf-model-inference']:
 h=json.loads((S/'health.json').read_text());r=next(r for r in h['rows'] if r['task']==task)
 p=Path(r['result']['trial'])/'verifier/test-stdout.txt'
 print('FAIL',task,p.read_text(errors='replace')[-2800:])
p=B/'tb2-three-arm50-retry2-20261018/jobs/retry2-tb50-09-dsh-torch-pipeline-parallelism/torch-pipeline-parallelism__Ksib3ke'
lines=(p/'agent/live/dsh.jsonl').read_text().splitlines()
print('DSH_FORMAT',lines[0][:1400]);print('DSH_END',lines[-1][:1500])
from harbor.trial.trial import Trial
print('FINALIZE',inspect.getsource(Trial._finalize))
print('DOCKER_IMAGES',subprocess.check_output(['docker','images','--filter','reference=*ksib3ke*','--format','{{.ID}} {{.Repository}}'],text=True))
