"""Build pinned task sources into owned images; no model calls."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parent
PREFIX = 'longcli-paired10-20261001'
TASKS = ['cs61_fa24_scheme', 'cs61_fa24_ants', 'cs61_fa24_cats',
         'cs61_fa24_hog', 'cs61_fa24_hw08', 'cmu15_445_p0',
         'cmu15_445_p1', 'cmu15_445_p2', 'ap1400_2_hw26', 'ap1400_2_hw35']

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            h.update(block)
    return h.hexdigest()

def save(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2), encoding='utf-8')
    temporary.replace(path)

def reserve():
    if shutil.disk_usage('/var/lib/docker').free < 120 * 2**30:
        raise RuntimeError('Docker filesystem below 120 GiB reserve; no unrelated cleanup')

def docker(*args):
    return subprocess.check_output(['docker', *map(str, args)], text=True)

def main():
    reserve()
    inputs = json.loads((ROOT/'input-manifest.json').read_text())
    for name, expected in inputs['files'].items():
        if sha(ROOT/name) != expected:
            raise RuntimeError('Pinned source changed: '+name)
    # Reuse only content-verified images already produced by THIS preparation.
    # Failed build logs are retained; retry does not launch or replay any model trial.
    images = json.loads((ROOT/'base-images.json').read_text()) if (ROOT/'base-images.json').exists() else {}
    for family in ('make-pytest', 'c-env'):
        if family in images:
            assert sha(ROOT/images[family]['archive'])==images[family]['sha256']
            assert docker('image','inspect',images[family]['tag'],'--format','{{.Id}}').strip()==images[family]['id']
            continue
        tag = PREFIX+'/'+family+':2015f37'
        with (ROOT/('build-'+family+'.log')).open('x') as log:
            subprocess.run(['docker', 'build', '--label', 'experiment='+PREFIX,
                '-f', str(ROOT/'upstream/longcli_dockerImage'/('Dockerfile.'+family+'-base')),
                '-t', tag, str(ROOT/'upstream/longcli_dockerImage')],
                stdout=log, stderr=subprocess.STDOUT, check=True, timeout=3600)
        ident = docker('image', 'inspect', tag, '--format', '{{.Id}}').strip()
        reserve()
        container = docker('create', '--label', 'experiment='+PREFIX, tag).strip()
        try:
            archive = ROOT/(family+'-rootfs.tar')
            subprocess.run(['docker', 'export', '-o', str(archive), container], check=True, timeout=600)
        finally:
            docker('rm', container)
        images[family] = dict(tag=tag, id=ident, archive=archive.name, sha256=sha(archive))
        save(ROOT/'base-images.json', images)
        print(json.dumps(dict(built=family, id=ident, model_calls=0)), flush=True)
    tasks = []
    import yaml
    for index, task in enumerate(TASKS):
        reserve()
        path = ROOT/'upstream/tasks_long_cli'/task
        text = (path/'Dockerfile').read_text()
        family = 'c-env' if 'tb/c-env:v0' in text else 'make-pytest'
        old = 'tb/'+family+':v0'
        if text.count(old) != 1:
            raise RuntimeError('Unexpected base declaration')
        definition = ROOT/('Dockerfile.'+task)
        definition.write_text(text.replace(old, images[family]['tag']))
        tag = PREFIX+'/task-'+task+':2015f37'
        log_path=ROOT/('build-'+task+'.log')
        if log_path.exists(): log_path=ROOT/('build-'+task+'-'+str(time.time_ns())+'.log')
        with log_path.open('x') as log:
            subprocess.run(['docker', 'build', '--label', 'experiment='+PREFIX,
                '-f', str(definition), '-t', tag, str(path)],
                stdout=log, stderr=subprocess.STDOUT, check=True, timeout=300)
        info = yaml.safe_load((path/'task.yaml').read_text())
        project = next(line.split()[1].lstrip('./') for line in text.splitlines()
                       if line.startswith('COPY ') and line.split()[1] not in ('attachments', 'INSTRUCTION.md'))
        row = dict(task=task, family=family, project=project, index=index,
            image=tag, image_id=docker('image','inspect',tag,'--format','{{.Id}}').strip(),
            wall_seconds=float(info['max_agent_timeout_sec']),
            test_seconds=float(info['max_test_timeout_sec']))
        tasks.append(row)
        print(json.dumps(dict(prepared=task, model_calls=0)), flush=True)
    manifest = dict(experiment=PREFIX, commit=inputs['commit'], tasks=tasks,
        methods=['bestfgs-v6.1','raw'], total_trials=20, workers=2,
        model='deepseek-flash', thinking='disabled', temperature=0,
        max_turns=800, max_tools=600, command_seconds=300, max_tokens=4096,
        context_limit=48000, base_images=images, created=time.time(),
        grading='Single final official grading, no online hidden feedback')
    save(ROOT/'protocol.json', manifest)
    print(json.dumps(dict(prepared=True, tasks=10, trials=20, model_calls=0)), flush=True)

if __name__ == '__main__':
    main()
