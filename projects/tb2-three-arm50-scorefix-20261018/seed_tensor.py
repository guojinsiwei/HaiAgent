"""Reuse exact torch 2.7.0 cache for the identical tensor verifier requirements."""
import json,subprocess,sys
from pathlib import Path
R=Path(__file__).resolve().parent
source=R/'dependency-cache/torch-pipeline-parallelism/dependencies.tar'
assert (source.parent/'ready.json').exists()
name='tb2-scorewarm-torch-tensor-parallelism'
exists=subprocess.run(['docker','inspect',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0
if exists:
 assert '--replace-own-unfinished-warmer' in sys.argv
 assert not (R/'dependency-cache/torch-tensor-parallelism/ready.json').exists()
 doc=json.loads(subprocess.check_output(['docker','inspect',name]))[0]
 assert doc['Config']['Labels'].get('kz.scorefix')=='20261018'
 # Only stop our keyless dependency downloader, never an experiment container.
 subprocess.run(['docker','rm','-f',name],check=True)
subprocess.run(['docker','run','-d','--name',name,'--label','kz.scorefix=20261018','--user','root','--entrypoint','sleep','alexgshaw/torch-tensor-parallelism:20251031','infinity'],check=True)
subprocess.run(['docker','cp',str(source),name+':/tmp/cache.tar'],check=True)
subprocess.run(['docker','exec',name,'sh','-ec','tar -xf /tmp/cache.tar -C /opt; rm /tmp/cache.tar'],check=True)
print('TENSOR_CACHE_SEEDED')
from warm_dependencies import one
print(json.dumps(one('torch-tensor-parallelism')))
