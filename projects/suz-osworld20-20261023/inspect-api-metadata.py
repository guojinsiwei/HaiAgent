from pathlib import Path
import json
import urllib.request
import urllib.error
root=Path(__file__).resolve().parent
key=(root/'secrets/api-key').read_text().strip()
for base in ['https://api.taotoken.net/token/v1']:
    req=urllib.request.Request(base+'/models',headers={'Authorization':'Bearer '+key})
    try:
        with urllib.request.urlopen(req,timeout=30) as response:
            data=json.load(response)
        matches=[row for row in data.get('data',[]) if 'glm-5.3-flash' in str(row.get('id',''))]
        print(json.dumps({'status':200,'matching_models':matches}))
    except urllib.error.HTTPError as exc:
        body=exc.read().decode(errors='replace').replace(key,'[REDACTED]')
        print(json.dumps({'status':exc.code,'body':body[:800]}))
