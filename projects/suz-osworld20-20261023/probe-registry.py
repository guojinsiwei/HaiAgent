import urllib.request,urllib.error,json,urllib.parse,concurrent.futures
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args):return None
root='https://registry-1.docker.io/v2/happysixd/osworld-docker'
with urllib.request.urlopen('https://auth.docker.io/token?service=registry.docker.io&scope=repository:happysixd/osworld-docker:pull',timeout=15) as r:token=json.load(r)['token']
digest='sha256:e706691a854dc732436c04d70e418c99abc2927e34c1692dce2fe59c57025847'
opener=urllib.request.build_opener(NoRedirect())
try:opener.open(urllib.request.Request(root+'/blobs/'+digest,headers={'Authorization':'Bearer '+token}),timeout=15)
except urllib.error.HTTPError as e:
    url=e.headers.get('Location');print('redirect host:',urllib.parse.urlsplit(url).hostname,flush=True)
    with urllib.request.urlopen(urllib.request.Request(url,headers={'Range':'bytes=0-1023'}),timeout=15) as r:
        print('range response',r.status,r.headers.get('Content-Length'),flush=True)
        print('bytes received',len(r.read(1024)),flush=True)
