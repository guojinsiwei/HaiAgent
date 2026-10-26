"""Read-only deployment acceptance; no model requests."""
import json
from pathlib import Path
import docker
from common import ROOT,deployment_hash
ready=json.loads((ROOT/'preflight-multistep/passed.json').read_text())
assert ready['deployment_sha256']==deployment_hash()
for p in (ROOT/'runs').glob('*/*/worker-status.json'):
    status=json.loads(p.read_text());directory=p.parent
    if status['stage'] not in {'preflight','running'}:continue
    rows=[json.loads(x) for x in (directory/'agent.jsonl').read_text().splitlines()] if (directory/'agent.jsonl').exists() else []
    actions=[x for x in rows if x['event']=='prediction']
    if (directory/'run-config.json').exists():
        cfg=json.loads((directory/'run-config.json').read_text())
        assert cfg['shared_budget']['total_limit_cny']==480 and cfg['shared_budget']['bucket_limit_cny']==8
        assert cfg['coordinate_type']=='absolute' and cfg['solver_model']==cfg['role_model']=='glm-5.3-flash'
    print(json.dumps({'mode':status['mode'],'task':status['id'],'stage':status['stage'],
        'predictions':len(actions),'last_actions':actions[-1]['actions'] if actions else None}))
containers=docker.from_env().containers.list(filters={'label':'experiment='+ROOT.name})
assert len(containers)<=2
for c in containers:
    host=c.attrs['HostConfig'];assert host['Runtime']=='runc' and not host.get('DeviceRequests')
    assert all('nvidia' not in str(x).lower() and '/dev/dri' not in str(x).lower() for x in host.get('Devices',[]))
    print(json.dumps({'container':c.short_id,'cpu_only':True,'cpu_limit':host['NanoCpus']/1e9,'memory_bytes':host['Memory']}))
