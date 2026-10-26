import json,hashlib
from pathlib import Path
import docker
root=Path('/data/share/lizh639/suz-osworld20-20261023')
for p in (root/'repair1-runs').glob('*/*/worker-status.json'):
 s=json.loads(p.read_text());folder=p.parent
 if s['stage']!='running':continue
 rows=[json.loads(x) for x in (folder/'agent.jsonl').read_text().splitlines()] if (folder/'agent.jsonl').exists() else []
 acts=[x for x in rows if x['event']=='prediction']
 print(json.dumps({'mode':s['mode'],'task':s['id'],'stage':s['stage'],'executed_batches_logged':len(acts),'last_actions':acts[-1]['actions'] if acts else None,'preflight':json.loads((folder/'preflight.json').read_text())}))
for c in docker.from_env().containers.list(filters={'label':'experiment=suz-osworld20-20261023'}):
 h=c.attrs['HostConfig'];assert h['Runtime']=='runc' and not h.get('DeviceRequests')
 assert all('nvidia' not in str(d).lower() and '/dev/dri' not in str(d).lower() for d in h.get('Devices',[]))
 print(json.dumps({'container':c.short_id,'cpu_only':True,'runtime':h['Runtime'],'nano_cpus':h.get('NanoCpus'),'memory':h.get('Memory')}))
for r in json.loads((root/'repair1-manifest.json').read_text())['runs']:
 assert hashlib.sha256((root/r['original_result']).read_bytes()).hexdigest()==r['original_sha256']
print('Original result hashes: unchanged')
