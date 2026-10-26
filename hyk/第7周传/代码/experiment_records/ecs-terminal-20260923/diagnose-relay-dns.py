import json
import urllib.request
for host in ('auth.docker.io','production.cloudfront.docker.com'):
    try:
        with urllib.request.urlopen('https://dns.google/resolve?name='+host+'&type=A&edns_client_subnet=0.0.0.0/0',timeout=15) as response:
            data=json.load(response)
            print(host,[(x.get('data'),x.get('TTL')) for x in data.get('Answer',[])])
    except Exception as error:
        print(host,type(error).__name__,str(error)[:250])
