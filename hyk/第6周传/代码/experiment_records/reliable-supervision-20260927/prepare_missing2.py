"""Prepare two replacement trials for disk-interrupted, unscored cells."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time

OLD = Path('/var/tmp/lizh639-lhtb-r4')
NEW = Path('/var/tmp/lizh639-lhtb-missing2-r5')
TASK = 'great-expectations-audit'
METHODS = ('bestfgs', 'raw')


def write(path, value):
    temp = path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    temp.replace(path)


def hashes(root):
    excluded = {'ready.json', 'health.json', 'summary.json'}
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob('*')) if p.is_file() and p.name not in excluded
            and '__pycache__' not in p.parts}


def main():
    if NEW.exists(): raise RuntimeError('Replacement directory already exists; inspect first')
    health = json.loads((OLD/'health.json').read_text())
    if health.get('state') != 'completed_with_errors' or health.get('active'):
        raise RuntimeError('Original experiment is not terminal')
    rows = json.loads((OLD/'summary-v2.json').read_text())
    failures = {(r.get('task'), r.get('method')): r for r in rows
                if r.get('infrastructure_error') == 'disk_reserve_exhausted_and_worker_interrupted'}
    expected = {(TASK, method) for method in METHODS}
    if set(failures) != expected:
        raise RuntimeError('Expected exactly the two disk-interrupted cells')
    if any(r.get('verifier_result') is not None for r in failures.values()):
        raise RuntimeError('A replacement target already has an official score')
    if shutil.disk_usage('/var/tmp').free < 120*2**30:
        raise RuntimeError('Insufficient replacement disk reserve')

    NEW.mkdir(mode=0o700)
    for name in ('bestfgs-project', 'hai-project'):
        shutil.copytree(OLD/name, NEW/name, ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copytree(OLD/'upstream/harbor', NEW/'upstream/harbor', ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copytree(OLD/'upstream/tasks'/TASK, NEW/'upstream/tasks'/TASK,
                    ignore=shutil.ignore_patterns('__pycache__'))
    for source in OLD.glob('*.py'):
        shutil.copy2(source, NEW/source.name)
    tools = Path(__file__).resolve().parent
    for name in ('prepare_missing2.py', 'missing2.py', 'launch_missing2.py'):
        shutil.copy2(tools/name, NEW/name)
    for name in ('images.json', 'verified-digests.json', 'PROTOCOL.md'):
        shutil.copy2(OLD/name, NEW/name)
    manifest = json.loads((OLD/'manifest.json').read_text())
    row = next(r for r in manifest['tasks'] if r['task'] == TASK)
    supplement = {'version':'lhtb-missing2-r5', 'task':row, 'methods':list(METHODS),
        'total_trials':2, 'origin_protocol_sha256':health['protocol_sha256'],
        'replacement_rule':'Only cells with no official result and documented disk-reserve interruption; one fresh attempt each.',
        'failed_records':[{k:v for k,v in failures[(TASK,m)].items()
                           if k in ('task','method','infrastructure_error','audit_sha256','recovery_action')}
                          for m in METHODS]}
    write(NEW/'supplement.json', supplement)
    sys.path[:0] = [str(NEW),str(NEW/'upstream/harbor/src'),str(NEW/'bestfgs-project/src'),str(NEW/'hai-project/src')]
    from control import config
    from prepare import write as control_write
    from harbor.models.job.config import JobConfig
    (NEW/'jobs').mkdir()
    for method in METHODS:
        job = config(row, method)
        JobConfig.model_validate(job)
        control_write(NEW/'jobs'/(job['job_name']+'.json'), job)
    source_hashes = hashes(NEW)
    ready = {'ready':True, 'version':'lhtb-missing2-r5', 'hashes':source_hashes,
        'protocol_sha256':hashlib.sha256(json.dumps(source_hashes,sort_keys=True).encode()).hexdigest(),
        'origin_protocol_sha256':health['protocol_sha256'], 'sealed_at':time.time(), 'model_calls':0}
    write(NEW/'ready.json', ready)
    print(json.dumps({'ready':True,'target':str(NEW),'trials':2,
                      'protocol_sha256':ready['protocol_sha256'],'model_calls':0}))


if __name__ == '__main__': main()
