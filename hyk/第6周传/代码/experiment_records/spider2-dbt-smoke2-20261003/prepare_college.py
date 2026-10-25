"""Prepare two public DBT tasks and isolate gold; no model calls."""
import hashlib
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from common import ROOT, save, sha
from spider_grader import official_matcher,metadata

COMMIT='cafb867313aab4e674652054198f383cf4018943'
MIRROR_COMMIT='82d1fb0c144d28b1fd9852006cee0a39e74bd4a8'
MIRROR='https://huggingface.co/datasets/harborframework/harbor-datasets/resolve/'+MIRROR_COMMIT
TASKS=[('asset001','asset.duckdb'),('asana001','asana.duckdb')]
IMAGE='spider2-dbt-smoke2-20261003/runtime:1'
SESSION=requests.Session()
SESSION.mount('https://',HTTPAdapter(max_retries=Retry(total=3,backoff_factor=1,
    status_forcelist=[408,429,500,502,503,504],allowed_methods=['HEAD','GET'])))


def fetch(remote,target):
    url=MIRROR+'/datasets/spider2-dbt/'+remote
    provenance=ROOT/'data-provenance.json'
    if target.exists() and provenance.exists():
        records=json.loads(provenance.read_text())['downloads']
        cached=next((r for r in records if r['url']==url and ROOT/r['path']==target),None)
        if cached:
            assert target.stat().st_size==cached['bytes'] and sha(target)==cached['sha256']
            return cached
    header=SESSION.head(url,allow_redirects=False,timeout=(15,30))
    header.raise_for_status()
    expected=header.headers.get('x-linked-etag','').strip('"')
    size=int(header.headers.get('x-linked-size','0'))
    assert len(expected)==64 and 0<size<256*2**20,'Missing mirror content identity'
    target.parent.mkdir(parents=True,exist_ok=True)
    if not target.exists():
        pending=target.with_name(target.name+'.part')
        with SESSION.get(url,stream=True,timeout=(15,60)) as response:
            response.raise_for_status()
            with pending.open('wb') as stream:
                for chunk in response.iter_content(1048576):
                    if chunk:stream.write(chunk)
                    if stream.tell()>size:raise RuntimeError('Download larger than declared data')
        assert pending.stat().st_size==size and sha(pending)==expected
        pending.replace(target)
    assert target.stat().st_size==size and sha(target)==expected
    return dict(path=str(target.relative_to(ROOT)),bytes=size,sha256=expected,url=url)


def main(revise=False):
    if (ROOT/'claims').exists() or (ROOT/'grades').exists() or (ROOT/'health-0.json').exists():
        raise RuntimeError('Never overwrite prepared or claimed task inputs')
    existing_runtime=None
    if (ROOT/'college-ready.json').exists():
        if not revise:raise RuntimeError('Already prepared; explicit unstarted qualification revision required')
        previous=ROOT/'initial-qualification';previous.mkdir(exist_ok=False)
        existing_runtime=json.loads((ROOT/'protocol.json').read_text())['runtime_image']
        for name in ('college-ready.json','protocol.json','grading-acceptance.json','solver-inputs.tar.gz'):
            (ROOT/name).rename(previous/name)
        shutil.copy2(ROOT/'data-provenance.json',previous/'data-provenance.json')
        save(previous/'reason.json',dict(reason='playbook001 unchanged starter already scores 1; exclude from paid smoke',
            paid_trials=0,model_calls=0))
    elif (ROOT/'initial-qualification/protocol.json').exists():
        existing_runtime=json.loads((ROOT/'initial-qualification/protocol.json').read_text())['runtime_image']
    actual=subprocess.check_output(['git','-C',str(ROOT/'upstream'),'rev-parse','HEAD'],text=True).strip()
    assert actual==COMMIT,'Official source revision changed'
    official=ROOT/'upstream/spider2-dbt'
    instructions={r['instance_id']:r for r in map(json.loads,
        (official/'examples/spider2-dbt.jsonl').read_text().splitlines())}
    downloads=[]
    for task,db in TASKS:
        downloads.append(fetch(task+'/environment/dbt_project/'+db,ROOT/'downloads'/task/db))
        downloads.append(fetch(task+'/tests/gold.duckdb',ROOT/'gold'/task/db))
        # Confirm the mirror uses the same official evaluation configuration.
        cached=ROOT/'downloads'/task/'mirror-config.json'
        if not cached.exists():
            response=SESSION.get(MIRROR+'/datasets/spider2-dbt/'+task+'/tests/config.json',timeout=(15,30))
            response.raise_for_status();save(cached,response.json())
        config=json.loads(cached.read_text())
        gold,params=metadata(task)
        assert all(config[k]==params[k] for k in ('condition_tabs','condition_cols','ignore_orders'))
        assert official_matcher()(str(gold),str(gold),**params)==1
    public=ROOT/'public';public.mkdir(exist_ok=True)
    rows=[]
    for index,(task,db) in enumerate(TASKS):
        base=public/task;base.mkdir(exist_ok=True)
        if not (base/task).exists():
            shutil.copytree(official/'examples'/task,base/task,symlinks=False)
            shutil.copy2(ROOT/'downloads'/task/db,base/task/db)
        assert sha(base/task/db)==sha(ROOT/'downloads'/task/db),'Starter database changed before solving'
        instruction=instructions[task]['instruction']
        (base/'INSTRUCTION.md').write_text(instruction+'\n\n'
            'Project directory: '+task+'. Complete the project and leave the final DuckDB database at '
            +task+'/'+db+'. The database begins with public source tables. '
            'Inspect the project and current database; do not assume output tables already exist. '
            'You may use dbt and Python/DuckDB. All work and final outputs must remain under /app.\n',encoding='utf-8')
        rows.append(dict(task=task,index=index,instruction=(base/'INSTRUCTION.md').read_text(),project=task,
                         result_path=task+'/'+db,wall_seconds=3600,cpu_affinity=[8,9]))
    protocol=dict(experiment='spider2-dbt-smoke2-20261003',benchmark='Spider2-DBT',commit=COMMIT,
        tasks=rows,methods=['prediction-off'],total_trials=2,workers=1,
        model='deepseek-flash',thinking='disabled',temperature=0,max_turns=400,max_tools=200,
        command_seconds=300,context_limit=48000,role_output_tokens=dict(action=4096,advisor=1536,monitor=1536),
        generation_concurrency_per_worker=1,generation_resources=dict(concurrency_total=1,cpu_affinity_each=2),
        adapted_smoke=True,full_official_benchmark=False,
        runtime_adaptation='Cached public Ubuntu/Python 3.12.3 base; isolated pinned DBT venv. Official baseline uses Python 3.11.',
        data_provenance=dict(source='Harbor registry mirror of Spider2 DBT databases',mirror_commit=MIRROR_COMMIT,
            direct_official_drive_unavailable=True,byte_parity_to_google_drive_unverified=True),
        network='Solver commands offline; public declared dbt packages installed before solving',
        result='Frozen final database graded with exact official DuckDB matcher; no hidden feedback while solving')
    save(ROOT/'protocol.json',protocol)
    save(ROOT/'data-provenance.json',dict(downloads=downloads,official_commit=COMMIT,mirror_commit=MIRROR_COMMIT,model_calls=0))
    # Docker only constructs an ordinary Python/DBT filesystem; Cube does not run Docker.
    cached_base=subprocess.check_output(['docker','image','inspect','longcli-paired10-20261001/make-pytest:2015f37',
        '--format','{{.Id}}'],text=True).strip()
    assert cached_base=='sha256:b287b885f05beae74d249992380c27298ab3584ad5a09367293945228aeeee0a'
    if not existing_runtime:
        with (ROOT/'build-runtime.log').open('a') as log:
            subprocess.run(['docker','build','--network','host','--label','experiment='+protocol['experiment'],'-t',IMAGE,
                '-f',str(ROOT/'Dockerfile'),str(ROOT)],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=1800)
    ident=subprocess.check_output(['docker','image','inspect',IMAGE,'--format','{{.Id}}'],text=True).strip()
    if existing_runtime:
        assert existing_runtime['id']==ident and sha(ROOT/existing_runtime['archive'])==existing_runtime['sha256']
    else:
        container=subprocess.check_output(['docker','create','--label','experiment='+protocol['experiment'],IMAGE],text=True).strip()
        try:
            subprocess.run(['docker','export','-o',str(ROOT/'runtime-rootfs.tar'),container],check=True,timeout=300)
        finally:
            subprocess.run(['docker','rm',container],check=True,timeout=60)
    # Provision only publicly declared dependencies; no model or scoring feedback.
    for task,db in TASKS:
        project=public/task/task
        if (project/'packages.yml').exists():
            with (ROOT/('dbt-deps-'+task+'.log')).open('a') as log:
                subprocess.run(['docker','run','--rm','--label','experiment='+protocol['experiment'],
                    '--cpus','2','--memory','3g','-v',str(project)+':/app','-w','/app',IMAGE,
                    'dbt','deps','--profiles-dir','.'],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=300)
    protocol['runtime_image']=dict(tag=IMAGE,id=ident,archive='runtime-rootfs.tar',sha256=sha(ROOT/'runtime-rootfs.tar'))
    save(ROOT/'protocol.json',protocol)
    checks=[]
    import duckdb
    for task,db in TASKS:
        gold,params=metadata(task)
        # Positive and missing-table fixtures exercise the exact scorer without a model.
        empty=ROOT/'downloads'/task/'empty-fixture.duckdb'
        con=duckdb.connect(str(empty));con.execute('create table if not exists unrelated(x int)');con.close()
        positive=official_matcher()(str(gold),str(gold),**params)
        negative=official_matcher()(str(empty),str(gold),**params)
        assert positive==1 and negative==0
        starter=official_matcher()(str(public/task/task/db),str(gold),**params)
        assert starter==0,'Unchanged starter already passes; do not spend model calls on this task'
        checks.append(dict(task=task,gold_self_match=positive,missing_table_match=negative,
                          unchanged_starter_score=starter,model_calls=0))
    save(ROOT/'grading-acceptance.json',dict(passed=True,checks=checks,model_calls=0))
    # Only task starter trees and controller code are packaged for the solver.
    files=list(ROOT.glob('*.py'))+[ROOT/'protocol.json',ROOT/'data-provenance.json']
    folders=[ROOT/'sources',ROOT/'compatibility']+[ROOT/'public'/task for task,db in TASKS]
    files += [p for folder in folders for p in folder.rglob('*')
              if p.is_file() and '__pycache__' not in p.parts]
    with tarfile.open(ROOT/'solver-inputs.tar.gz','x:gz') as archive:
        for p in files:archive.add(p,arcname=p.relative_to(ROOT).as_posix(),recursive=False)
    grader_files=[ROOT/'spider_grader.py',ROOT/'common.py',ROOT/'protocol.json',
        official/'evaluation_suite/eval_utils.py',official/'evaluation_suite/gold/spider2_eval.jsonl']
    grader_files += [ROOT/'gold'/task/db for task,db in TASKS]
    save(ROOT/'college-ready.json',dict(ready=True,hashes={p.relative_to(ROOT).as_posix():sha(p) for p in grader_files},model_calls=0))
    print(json.dumps(dict(prepared=True,tasks=2,model_calls=0,solver_archive_bytes=(ROOT/'solver-inputs.tar.gz').stat().st_size,
                         runtime_archive_bytes=(ROOT/'runtime-rootfs.tar').stat().st_size)),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--revise-unstarted',action='store_true')
    args=parser.parse_args();main(args.revise_unstarted)
