"""Fetch the pinned full benchmark, build missing official images, stage public COPY inputs."""
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import time
import yaml
from common import ROOT, save, sha, export_tree

COMMIT='2015f37b5c458f2562354de6b415e9182c91af64'
OLD=Path('/var/tmp/lizh639-longcli-prediction-toggle10-20261003')

def docker(*args,seconds=120):
    return subprocess.check_output(['docker',*map(str,args)],text=True,timeout=seconds).strip()

def main():
    assert not (ROOT/'college-ready.json').exists() and not (ROOT/'claims').exists()
    archive=ROOT/'upstream-pinned.tar.gz'
    if not archive.exists():
        subprocess.run(['curl','--fail','--location','--retry','2','--max-time','180',
            'https://codeload.github.com/finyorko/longcli-bench/tar.gz/'+COMMIT,
            '-o',str(archive)],check=True,timeout=200)
    upstream=ROOT/'upstream'
    if not upstream.exists():
        unpack=ROOT/'upstream-unpack';unpack.mkdir(exist_ok=False)
        with tarfile.open(archive) as stream:stream.extractall(unpack,filter='data')
        source=unpack/('longcli-bench-'+COMMIT)
        assert source.is_dir()
        source.rename(upstream)
    # Previously used official tests and starters must be byte-identical.
    prior=json.loads((OLD/'input-manifest.json').read_text())
    checked=0
    for name,digest in prior['files'].items():
        if name.startswith('upstream/'):
            assert sha(ROOT/name)==digest,'Pinned upstream mismatch: '+name
            checked+=1
    p=json.loads((ROOT/'previous-protocol.json').read_text())
    old_tasks=p['tasks']
    tasks=[r['task'] for r in old_tasks]+sorted(d.name for d in (upstream/'tasks_long_cli').iterdir()
        if d.is_dir() and d.name.startswith('61810_'))
    assert len(tasks)==len(set(tasks))==20
    public=ROOT/'public';public.mkdir(exist_ok=True)
    rows=[]
    for index,task in enumerate(tasks):
        source=upstream/'tasks_long_cli'/task
        text=(source/'Dockerfile').read_text()
        family='c-env' if 'FROM tb/c-env:v0' in text else 'make-pytest'
        info=yaml.safe_load((source/'task.yaml').read_text())
        names=[line.split()[1].removeprefix('./') for line in text.splitlines() if line.startswith('COPY ')]
        assert all(n not in ('tests','run-tests.sh') and '/' not in n for n in names)
        project=next(n for n in names if n not in ('attachments','INSTRUCTION.md'))
        target=public/task
        if not target.exists():
            target.mkdir()
            for name in names:
                original=source/name
                if original.is_dir():shutil.copytree(original,target/name,symlinks=True)
                else:shutil.copy2(original,target/name)
        assert (target/'INSTRUCTION.md').is_file()
        prior_row=next((r for r in old_tasks if r['task']==task),None)
        if prior_row:
            tag=prior_row['image'];ident=docker('image','inspect',tag,'--format','{{.Id}}')
            assert ident==prior_row['image_id']
        else:
            tag='longcli-dh-raw-full20-20261004/task-'+task+':2015f37'
            marker=ROOT/('image-'+task+'.json')
            if marker.exists():
                ident=json.loads(marker.read_text())['image_id']
                assert docker('image','inspect',tag,'--format','{{.Id}}')==ident
            else:
                base='tb/'+family+':v0'
                assert text.count(base)==1
                definition=ROOT/('Dockerfile.'+task)
                definition.write_text(text.replace(base,p['base_images'][family]['tag']))
                with (ROOT/('build-'+task+'-'+str(time.time_ns())+'.log')).open('x') as log:
                    subprocess.run(['docker','build','--label','experiment=longcli-dh-raw-full20-20261004',
                        '-f',str(definition),'-t',tag,str(source)],check=True,stdout=log,
                        stderr=subprocess.STDOUT,timeout=600)
                ident=docker('image','inspect',tag,'--format','{{.Id}}')
                save(marker,dict(image_id=ident,task=task))
        rows.append(dict(task=task,family=family,project=project,index=index,image=tag,image_id=ident,
            wall_seconds=float(info['max_agent_timeout_sec']),test_seconds=float(info['max_test_timeout_sec']),
            instruction=info['instruction']))
        print(json.dumps(dict(prepared=task,model_calls=0)),flush=True)
    p.update(experiment='longcli-dh-raw-full20-20261004',tasks=rows,methods=['dh','raw'],total_trials=40,
        created_date='2026-10-04',source_releases=dict(dh='recovery-counter-fix-v9 (v9 repair + recovery clock)',
        raw='frozen RAW executor/runtime + common repaired wire'),
        contrastive_predictions=False,route_search=False,
        context_windows=dict(dh='48000 characters, native memory protection',raw='48000 characters, RAW history'),
        assignment='Paired rotating arm order, 20 fresh jobs per worker, two slots each',
        status='preparing_not_started',ablation_only_difference=None,
        budget_definition='800 total logical decision requests across DH roles; wire retries separately audited; 600 actual tools',
        pilot_policy='First four trials (scheme/ants paired) are included in full results; engineering-only admission guard',
        original_task_inputs_identical=True,prior_results_carried=0)
    save(ROOT/'protocol.json',p)
    files=[f for folder in ('tasks_long_cli','terminal_bench','longcli_dockerImage')
        for f in (upstream/folder).rglob('*') if f.is_file() and '__pycache__' not in f.parts]
    save(ROOT/'input-manifest.json',dict(commit=COMMIT,files={f.relative_to(ROOT).as_posix():sha(f) for f in files},
        archive_sha256=sha(archive),prior_official_files_verified=checked))
    bundle=ROOT/'public-inputs.tar.gz'
    if not bundle.exists():export_tree(public,bundle)
    save(ROOT/'public-input-manifest.json',dict(files={f.relative_to(ROOT).as_posix():sha(f)
        for f in public.rglob('*') if f.is_file()},archive_sha256=sha(bundle),hidden_tests_transferred=False))
    print(json.dumps(dict(prepared=True,tasks=20,trials=40,model_calls=0,public_bytes=bundle.stat().st_size)),flush=True)

if __name__=='__main__':main()
