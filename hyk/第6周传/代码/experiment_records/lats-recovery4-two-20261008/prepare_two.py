"""Prepare two fresh LATS attempts, preserving eighteen verified reports."""
import hashlib
import json
from pathlib import Path
import shutil
import time

ROOT = Path(__file__).resolve().parent
OLD = Path('/var/tmp/lizh639-lats-recovery3-six-20261008')
TASKS = {'cmu15_445_p0', '61810_fs'}

def read(path):
    return json.loads(path.read_text())

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False))

def owned_alive(pid):
    if not isinstance(pid, int) or pid <= 0:
        return False
    process = Path('/proc') / str(pid)
    try:
        return (process.stat().st_uid == OLD.stat().st_uid
                and process.joinpath('stat').read_text().rsplit(')', 1)[1].split()[0] != 'Z'
                and (str(OLD) in process.joinpath('cmdline').read_bytes().decode(errors='replace')
                     or process.joinpath('cwd').resolve().is_relative_to(OLD)))
    except (OSError, ValueError):
        return False

def main():
    assert ROOT == Path('/var/tmp/lizh639-lats-recovery4-two-20261008')
    assert not (ROOT/'resume-plan.json').exists(), 'Never overwrite a prepared campaign'
    assert not owned_alive(read(OLD/'health.json').get('pid'))
    old_plan = read(OLD/'resume-plan.json')
    preserved = {row['task']: row for row in old_plan['preserved']}
    for path in (OLD/'grades').glob('lats--*/result.json'):
        report = read(path)
        if report.get('grading_state') == 'complete' and report.get('grading_container_destroyed'):
            preserved[report['task']] = {'task': report['task'], 'report': str(path),
                                         'report_sha256': sha(path)}
    remaining = [row for row in old_plan['run_tasks'] if row['task'] not in preserved]
    assert {row['task'] for row in remaining} == TASKS and len(preserved) == 18
    for row in remaining:
        job = OLD/'jobs'/('lats--'+row['task'])
        assert not owned_alive(read(job/'health.json').get('pid'))
        assert not (OLD/'grades'/job.name/'result.json').exists()
    for row in preserved.values():
        assert sha(Path(row['report'])) == row['report_sha256']
    for path in OLD.glob('*.py'):
        shutil.copyfile(path, ROOT/path.name)
    for name in ('upstream', 'input-manifest.json', 'sources', 'compatibility', 'taco_native'):
        path = OLD/name
        if path.exists():
            (ROOT/name).symlink_to(path.resolve(), target_is_directory=path.is_dir())
    for name in ('jobs', 'grades', 'incoming', 'host-tmp', 'empty-tests', 'acceptance-jobs'):
        (ROOT/name).mkdir()
    shutil.copyfile(OLD/'failure-fixtures.json', ROOT/'failure-fixtures.json')
    protocol = read(OLD/'protocol.json')
    protocol.update(experiment=ROOT.name, tasks=remaining, run_tasks=remaining,
                    total_trials=2, concurrency=2)
    protocol['recovery4'] = {'preserved_grades': 18, 'fresh_attempts': 2,
                             'source': str(OLD), 'model_and_budgets_unchanged': True,
                             'official_feedback_to_solver': False}
    save(ROOT/'protocol.json', protocol)
    save(ROOT/'resume-plan.json', {'method': 'lats', 'root': str(ROOT), 'source': str(OLD),
         'concurrency': 2, 'preserved': list(preserved.values()),
         'run_tasks': remaining, 'time': time.time()})
    # Every solver/transport/grader module is identical to the previous accepted copy.
    inherited = {path.name: sha(path) for path in OLD.glob('*.py')}
    assert all(sha(ROOT/name) == value for name, value in inherited.items())
    save(ROOT/'inherited-code.json', {'source': str(OLD), 'sha256': inherited,
                                     'time': time.time(), 'paid_model_calls': 0})
    print(json.dumps({'prepared': True, 'preserved': 18, 'rerun': sorted(TASKS),
                      'concurrency': 2, 'paid_model_calls': 0}))

if __name__ == '__main__':
    main()
