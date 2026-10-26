"""Assemble from the sealed historic run, never from a moving release tree."""
from pathlib import Path
import hashlib
import json
import shutil
from common import ROOT, save, sha

ORIGINAL = Path('/var/tmp/longcli-dh-routing3x7-20261008')
BASE = Path('/var/tmp/lizh639-longcli-dh-raw-full20-20261004')


def main():
    original_ready = json.loads((ORIGINAL/'ready.json').read_text())
    for name, expected in original_ready['hashes'].items():
        assert sha(ORIGINAL/name) == expected, 'Historic seal changed: ' + name
    historical = json.loads((ORIGINAL/'protocol.json').read_text())
    full = json.loads((BASE/'protocol.json').read_text())
    assert full['commit'] == historical['commit']
    preserved = [r['task'] for r in historical['tasks']]
    remaining = [r for r in full['tasks'] if r['task'] not in preserved]
    assert len(remaining) == 13 and len(preserved) == 7
    assert len(set(preserved) | {r['task'] for r in remaining}) == 20
    for name in ('sources', 'compatibility', 'tests'):
        shutil.copytree(ORIGINAL/name, ROOT/name,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    for f in ORIGINAL.glob('*.py'):
        if f.name in {'package.py', 'prepare_local.py', 'setup_remote.py', 'launch.py', 'accept.py', 'status.py', 'run_worker.py'}:
            continue
        target = ROOT/f.name
        if target.exists():
            assert sha(target) == sha(f)
        else:
            shutil.copyfile(f, target)
    for name in ('upstream', 'input-manifest.json'):
        (ROOT/name).symlink_to(BASE/name, target_is_directory=(BASE/name).is_dir())
    for name in ('jobs', 'grades', 'incoming', 'acceptance-jobs', 'host-tmp', 'evidence', 'empty-tests'):
        (ROOT/name).mkdir(exist_ok=True)
    p = dict(historical, experiment=ROOT.name, methods=['1342'], tasks=remaining,
        total_trials=13, concurrency=6, concurrency_per_arm=6,
        task_selection='complement of historic seven, no score-based filtering',
        preserved_original_tasks=preserved)
    save(ROOT/'protocol.json', p)
    preserved_rows = []
    for task in preserved:
        file = ORIGINAL/'grades'/('1342--'+task)/'result.json'
        assert json.loads(file.read_text())['grading_state'] == 'complete'
        preserved_rows.append(dict(task=task, report=str(file), sha256=sha(file)))
    fixed = {name: sha(ROOT/name) for name in original_ready['hashes']
             if name.startswith(('sources/', 'compatibility/')) or name in
             ('runner.py', 'repair_runtime.py', 'budget_adapter.py', 'docker_environment.py',
              'environment.py', 'shared_wire.py', 'grade_one.py', 'grading_adapter.py', 'college_grader.py')}
    for name, expected in fixed.items():
        assert expected == original_ready['hashes'][name]
    save(ROOT/'source-provenance.json', dict(original=str(ORIGINAL),
        unchanged_solver_and_environment=True, fixed_hashes=fixed,
        original_protocol_sha256=sha(ORIGINAL/'protocol.json'),
        scheduler_only_changes=['single-arm pilot', 'isolate single-task faults', 'independent grader'],
        budget_unchanged=True, merged20_preserved=preserved_rows))
    print(json.dumps(dict(prepared=True, remaining=[r['task'] for r in remaining], preserved=7,
                         unchanged_source_files=len(fixed), paid_model_calls=0)))


if __name__ == '__main__':
    main()
