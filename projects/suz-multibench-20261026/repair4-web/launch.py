"""CPU-only, isolated trials. Environment preflights precede any paid run."""
import argparse,concurrent.futures,hashlib,json,os,time,uuid
from pathlib import Path
import docker,requests
import sys

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'harness'))
from cpu_contract import validate_cpu_host
CLIENT=docker.from_env(timeout=120)
LABELS={'owner':'lizh639','experiment':'suz-multibench-20261026'}
SECRET=Path('/data/share/lizh639/suz-osworld30-20261024/secrets/api-key')
WEB='suz-web-ready:20261026';ANDROID='suz-android-ready:20261026'
SITES={s:'docker.1ms.run/am1n3e/webarena-verified-'+s+':latest' for s in ['reddit','shopping']}

def write(path,data):
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(data,indent=2));temp.replace(path)

def fingerprint(benchmark):
    h=hashlib.sha256()
    source=[p for p in (ROOT/'SUZ').rglob('*') if p.is_file() and p.suffix in ['.py','.mjs','.json'] and '__pycache__' not in p.parts]
    for path in sorted([*source,*ROOT.joinpath('harness').glob('*.py'),ROOT/'launch.py',ROOT/'model-config.json',*ROOT.joinpath('tasks').glob(benchmark+'-*.json')]):
        h.update(str(path.relative_to(ROOT)).encode());h.update(path.read_bytes())
    for name in ([WEB,*SITES.values()] if benchmark=='webarena' else [ANDROID]):
        h.update(CLIENT.images.get(name).id.encode())
    return h.hexdigest()

def check_cpu(container):
    container.reload();host=container.attrs['HostConfig']
    validate_cpu_host(host)

def trial(benchmark,path,mode,preflight=False):
    spec=json.loads(path.read_text());taskid=spec['id']
    out=ROOT/('preflight' if preflight else 'runs')/benchmark/mode/taskid
    if out.exists():
        previous=out/'deployment.json'
        if preflight and previous.exists():
            prior=json.loads(previous.read_text())
            if prior.get('status')=='preflight_passed' and prior.get('fingerprint')==fingerprint(benchmark):return prior
        raise RuntimeError('Refusing replay of existing trial '+str(out))
    out.mkdir(parents=True)
    name='suz-mb-'+uuid.uuid4().hex[:12];network=None;site=None;worker=None
    record={'task':taskid,'mode':mode,'benchmark':benchmark,'preflight':preflight,'started':time.time(),'fingerprint':fingerprint(benchmark)}
    try:
        env={'CUDA_VISIBLE_DEVICES':'','NVIDIA_VISIBLE_DEVICES':'void'}
        if benchmark=='webarena':
            site_name=spec['task']['sites'][0]
            network=CLIENT.networks.create(name,labels=LABELS)
            site=CLIENT.containers.create(SITES[site_name],name=name+'-site',detach=True,runtime='runc',
                labels=LABELS,mem_limit='8g',nano_cpus=3_000_000_000,environment={'WA_ENV_CTRL_EXTERNAL_SITE_URL':'http://site/'},ports={'80/tcp':('127.0.0.1',None),'8877/tcp':('127.0.0.1',None)})
            network.connect(site,aliases=['site']);site.start();check_cpu(site)
            record.update(site=site.name,network=network.name,site_image=site.image.id)
            write(out/'deployment.json',record)
            site.reload();ports=site.attrs['NetworkSettings']['Ports']
            url='http://127.0.0.1:'+ports['80/tcp'][0]['HostPort']
            control='http://127.0.0.1:'+ports['8877/tcp'][0]['HostPort']
            for _ in range(120):
                try:
                    response=requests.get(control+'/status',timeout=8)
                    if response.ok and response.json().get('success'):break
                except (requests.RequestException,ValueError):pass
                time.sleep(5)
            else:raise RuntimeError('Website services did not become healthy')
            if site_name=='reddit':
                # This image's HTTP /init calls ops.init() without the required
                # base_url. Its official CLI supports the missing argument.
                executed=site.exec_run(['/usr/local/bin/env-ctrl','--verbose','init','--base-url','http://site/'],demux=True)
                assert executed.exit_code==0,'Official Reddit initialization failed'
                receipt=json.loads(executed.output[0].decode())
            else:
                initialized=requests.post(control+'/init',timeout=180);initialized.raise_for_status()
                receipt=initialized.json()
            write(out/'site-initialization.json',receipt)
            assert receipt.get('success'),'Website initialization rejected'
            # Website startup may initialize a large DB; readiness has no model calls.
            ok=False
            for _ in range(180):
                try:
                    response=requests.get(url,headers={'Host':'site'},allow_redirects=False,timeout=8)
                    if response.status_code==200 and len(response.content)>500:ok=True;break
                except requests.RequestException:pass
                site.reload()
                if site.status!='running':break
                time.sleep(5)
            if not ok:raise RuntimeError('Website readiness failed; retained site container')
            for key in ['REDDIT','SHOPPING','SHOPPING_ADMIN','GITLAB','WIKIPEDIA','MAP','HOMEPAGE']:
                env[key]='http://site' if key.lower()==site_name else 'http://unused-'+key.lower()
            encoded=json.dumps(spec)
            for key,value in env.items():
                if key not in ['CUDA_VISIBLE_DEVICES','NVIDIA_VISIBLE_DEVICES']:encoded=encoded.replace('__'+key+'__',value)
            spec=json.loads(encoded)
        write(out/'task.json',spec)
        volumes={str(ROOT):{'bind':'/campaign','mode':'rw'},str(out):{'bind':'/output','mode':'rw'},str(ROOT/'harness'):{'bind':'/opt/harness','mode':'ro'}}
        if not preflight:
            gate=json.loads((ROOT/('ready-'+benchmark+'.json')).read_text())
            assert gate['passed'] and gate['fingerprint']==fingerprint(benchmark),'Stale or missing preflight gate'
            volumes[str(SECRET)]={'bind':'/secret/api-key','mode':'ro'}
            volumes[str(ROOT.parent/'accounting')]={'bind':'/accounting','mode':'rw'}
        command=['python','-u','/opt/harness/worker.py','--benchmark',benchmark,'--task','/output/task.json','--mode',mode]
        if preflight:command+=['--preflight']
        options=dict(name=name+'-worker',command=command,detach=True,runtime='runc',labels=LABELS,
                     volumes=volumes,environment=env,mem_limit='8g',nano_cpus=4_000_000_000,shm_size='1g')
        if network:options['network']=network.name
        if benchmark=='androidworld':
            options['devices']=['/dev/kvm:/dev/kvm:rwm'];options['nano_cpus']=6_000_000_000
        worker=CLIENT.containers.run(WEB if benchmark=='webarena' else ANDROID,**options);check_cpu(worker)
        record.update(worker=worker.name,site=site.name if site else None,network=network.name if network else None,
                      image=worker.image.id,site_image=site.image.id if site else None)
        write(out/'deployment.json',record)
        deadline=time.monotonic()+(1800 if preflight else 8500)
        while time.monotonic()<deadline:
            worker.reload()
            if worker.status in ['exited','dead']:break
            time.sleep(5)
        else:
            worker.stop(timeout=30);raise RuntimeError('Worker watchdog timeout; container retained')
        (out/'container.log').write_bytes(worker.logs())
        result=json.loads((out/'result.json').read_text()) if (out/'result.json').exists() else {}
        state=json.loads((out/'worker-status.json').read_text()) if (out/'worker-status.json').exists() else {}
        if preflight:assert result.get('passed') and state.get('stage')=='preflight_passed',state
        else:assert result.get('official_score') is not None and not result.get('error'),state
        record.update(status='preflight_passed' if preflight else 'completed',result=result)
        # Stopped containers preserve final filesystem and grader recovery state.
    except Exception as exc:
        record.update(status='engineering_failure',error=type(exc).__name__+': '+str(exc)[:1000])
    finally:
        if worker:
            try:
                worker.reload()
                if worker.status=='running':worker.stop(timeout=30)
                (out/'container.log').write_bytes(worker.logs())
            except Exception:pass
        if site:
            try:site.stop(timeout=30)
            except Exception:pass
        if network:
            try:
                network.reload()
                write(out/'network-inspect.json',network.attrs)
                owned=[obj for obj in [worker,site] if obj]
                for obj in owned:obj.reload()
                if not network.attrs.get('Containers') and all(obj.status in ['exited','dead','created'] for obj in owned):
                    network.remove();record['network_released']=True
            except Exception as exc:record['network_cleanup_error']=type(exc).__name__+': '+str(exc)[:200]
        record['finished']=time.time();write(out/'deployment.json',record)
    print(json.dumps({k:record.get(k) for k in ['benchmark','task','mode','status','error']}),flush=True)
    return record

def main():
    p=argparse.ArgumentParser();p.add_argument('phase',choices=['preflight','run']);p.add_argument('benchmark',choices=['webarena','androidworld']);p.add_argument('--concurrency',type=int,default=2);args=p.parse_args()
    assert 1<=args.concurrency<=4
    tasks=sorted((ROOT/'tasks').glob(args.benchmark+'-*.json'));assert len(tasks)==10
    if args.phase=='preflight':
        results=[];pending=iter(tasks);failed=False
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            futures=set()
            for _ in range(args.concurrency):
                path=next(pending,None)
                if path:futures.add(pool.submit(trial,args.benchmark,path,'opencua_baseline',True))
            while futures:
                done,_=concurrent.futures.wait(futures,return_when=concurrent.futures.FIRST_COMPLETED)
                for future in done:
                    row=future.result();results.append(row);futures.remove(future)
                    if row['status']!='preflight_passed':failed=True
                if not failed:
                    while len(futures)<args.concurrency:
                        path=next(pending,None)
                        if path is None:break
                        futures.add(pool.submit(trial,args.benchmark,path,'opencua_baseline',True))
        passed=len(results)==len(tasks) and all(row['status']=='preflight_passed' for row in results)
        write(ROOT/('ready-'+args.benchmark+'.json'),{'passed':passed,'fingerprint':fingerprint(args.benchmark),'time':time.time(),'model_calls':0,'checks':results})
        if not passed:raise RuntimeError('Preflight failed; paid phase blocked')
    else:
        gate=json.loads((ROOT/('ready-'+args.benchmark+'.json')).read_text())
        assert gate['passed'] and gate['fingerprint']==fingerprint(args.benchmark)
        # First pair is a paid canary, counted in the same 40 runs and budget.
        arms=['opencua_baseline','suz']
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            first=list(pool.map(lambda arm:trial(args.benchmark,tasks[0],arm),arms))
            if any(row['status']=='engineering_failure' for row in first):raise RuntimeError('Canary engineering failure; remaining tasks held')
            pending=[(path,arm) for path in tasks[1:] for arm in arms]
            # Drain only active work if an engineering failure occurs.
            futures={};index=0;failed=False
            while futures or (index<len(pending) and not failed):
                while len(futures)<args.concurrency and index<len(pending) and not failed:
                    path,arm=pending[index];index+=1;futures[pool.submit(trial,args.benchmark,path,arm)]=(path,arm)
                done,_=concurrent.futures.wait(futures,return_when=concurrent.futures.FIRST_COMPLETED)
                for future in done:
                    result=future.result();del futures[future]
                    if result['status']=='engineering_failure':failed=True
            write(ROOT/('queue-'+args.benchmark+'.json'),{'finished':time.time(),'held_for_engineering':failed,'unstarted':len(pending)-index})

if __name__=='__main__':main()
