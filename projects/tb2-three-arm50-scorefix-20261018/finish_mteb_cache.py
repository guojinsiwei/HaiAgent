import json,subprocess
from pathlib import Path
R=Path(__file__).resolve().parent;name='tb2-scorewarm-mteb-retrieve'
if not (R/'dependency-cache/mteb-retrieve/ready.json').exists():
 doc=json.loads(subprocess.check_output(['docker','inspect',name]))[0]
 assert doc['Config']['Labels'].get('kz.scorefix')=='20261018'
 subprocess.run(['docker','stop','-t','3',name],check=True)
 subprocess.run(['docker','start',name],check=True)
 from warm_dependencies import one
 print(json.dumps(one('mteb-retrieve')))
