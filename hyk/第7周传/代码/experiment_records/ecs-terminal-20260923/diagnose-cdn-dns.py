import json
import urllib.request
import time

host='production.cloudfront.docker.com'
for endpoint in [
    'https://8.8.8.8/resolve?name='+host+'&type=A',
    'https://dns.alidns.com/resolve?name='+host+'&type=A',
    'https://8.8.8.8/resolve?name='+host+'&type=A&edns_client_subnet=154.213.1.0/24',
    'https://8.8.8.8/resolve?name='+host+'&type=A&edns_client_subnet=58.249.112.0/24',
]:
    try:
        with urllib.request.urlopen(endpoint,timeout=12) as response:
            data=json.load(response)
        print(json.dumps({'endpoint':endpoint,'answers':[x.get('data') for x in data.get('Answer',[]) if x.get('type')==1]}),flush=True)
    except Exception as e: print(type(e).__name__,flush=True)
