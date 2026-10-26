"""Download public task and grading files before model calls. Do not expose gold files to agents."""
from pathlib import Path
import hashlib
import json
import os
import urllib.request
import uuid
import concurrent.futures

ROOT=Path(__file__).resolve().parent


def prefetch(task):
    cache=ROOT/'assets'/task['id'];cache.mkdir(parents=True,exist_ok=True)
    resources=[]
    for action in task.get('config',[])+task.get('evaluator',{}).get('postconfig',[]):
        if action.get('type')=='download':
            for item in action['parameters']['files']:
                resources.append((item['url'],str(uuid.uuid5(uuid.NAMESPACE_URL,item['url']))+'_'+os.path.basename(item['path']),None))
    def scan(value):
        if isinstance(value,list):
            for item in value:scan(item)
        elif isinstance(value,dict):
            if value.get('type')=='cloud_file':
                paths=value['path'] if value.get('multi') else [value['path']]
                dests=value['dest'] if value.get('multi') else [value['dest']]
                hashes=value.get('sha256') if value.get('multi') else [value.get('sha256')]
                resources.extend(zip(paths,dests,hashes or [None]*len(paths)))
            for child in value.values():scan(child)
    scan(task.get('evaluator',{}))
    record=[]
    for url,dest,expected in resources:
        target=(cache/dest).resolve()
        if not target.is_relative_to(cache.resolve()):raise ValueError('Invalid cache destination')
        target.parent.mkdir(parents=True,exist_ok=True)
        mirror=url.replace('https://huggingface.co/','https://hf-mirror.com/')
        if not target.exists():
            partial=target.with_name(target.name+'.partial')
            sources=[url,mirror] if os.name=='nt' else [mirror,url]
            for attempt,source in enumerate(sources*2):
                try:
                    request=urllib.request.Request(source,headers={'User-Agent':'SUZ-OSWorld-preflight/1'})
                    with urllib.request.urlopen(request,timeout=20) as response,partial.open('wb') as out:
                        while block:=response.read(65536):out.write(block)
                    break
                except Exception:
                    if attempt==3:raise
            partial.replace(target)
        digest=hashlib.sha256(target.read_bytes()).hexdigest()
        if expected and digest!=expected:raise ValueError('Official asset checksum mismatch')
        record.append({'url':url,'download_url':mirror,'file':str(Path('assets')/task['id']/target.relative_to(cache.resolve())),
                       'sha256':digest,'bytes':target.stat().st_size})
    (cache/'download-manifest.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
    return record


if __name__=='__main__':
    manifest=json.loads((ROOT/'task-manifest.json').read_text())
    results=[]
    def fetch(row):
        try:
            result={'id':row['id'],'ok':True,'files':len(prefetch(json.loads((ROOT/row['path']).read_text())))}
        except Exception as exc:
            result={'id':row['id'],'ok':False,'error':type(exc).__name__+': '+str(exc)[:250]}
        print(json.dumps(result),flush=True);return result
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(fetch,manifest['tasks']))
    (ROOT/'assets-preflight.json').write_text(json.dumps(results,indent=2))
    if not all(row['ok'] for row in results):raise SystemExit(1)
