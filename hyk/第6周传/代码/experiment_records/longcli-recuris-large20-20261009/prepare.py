"""Fresh full-20 deployment from the sealed Recuris large-7 source, no API."""
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent
SOURCE_ROOT = Path('/mnt/sdb/home/lizh639/longcli-recuris-taco-large7-20261009')
SOURCE = SOURCE_ROOT / 'recuris_frozen'
BASE = Path('/var/tmp/lizh639-longcli-dh-raw-full20-20261004')
RESOURCE_FIELDS = ('model', 'temperature', 'max_tokens', 'context_tokens',
                   'context_headroom_tokens', 'actual_api_attempts_per_task',
                   'max_tools', 'wall_seconds', 'command_seconds')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    sealed = json.loads((SOURCE_ROOT / 'ready.json').read_text())
    assert sealed['ready']
    for name, expected in sealed['hashes'].items():
        if name.startswith('recuris_frozen/') or name == 'protocol.json':
            assert sha(SOURCE_ROOT / name) == expected, name
    reference = json.loads((SOURCE_ROOT / 'protocol.json').read_text())
    full = json.loads((BASE / 'protocol.json').read_text())
    tasks = full['tasks']
    assert len(tasks) == len({r['task'] for r in tasks}) == 20
    # Keep the same delivery canary as the previous large-budget experiment.
    tasks = sorted(tasks, key=lambda r: (r['task'] != 'cs61_fa24_hog', r['index']))
    tasks = [dict(r, wall_seconds=reference['wall_seconds']) for r in tasks]
    by_task = {r['task']: r for r in tasks}
    for row in reference['tasks']:
        assert by_task[row['task']] == row, 'Task input drift: ' + row['task']
    protocol = {k: reference[k] for k in RESOURCE_FIELDS}
    protocol.update(experiment=ROOT.name, commit=full['commit'], tasks=tasks,
        methods=['recuris_frozen'], total_trials=20, max_turns=800,
        concurrency=6, concurrency_per_arm=6, cross_task_memory=False,
        thinking=False, source_reference=str(SOURCE_ROOT),
        context_meter=reference['context_meter'], cpu_per_task=2,
        memory_gib_per_task=8, pids_limit=256,
        baseline_modes={'recuris_frozen': reference['baseline_modes']['recuris_frozen']},
        official_feedback_to_solver=False, notifications={'enabled': False},
        paid_task_retries=0, prior_results_carried=0,
        included_canary='cs61_fa24_hog', cost_bar_cny=None)
    (ROOT / 'protocol.json').write_text(json.dumps(protocol, indent=2))
    arm = ROOT / 'recuris_frozen'
    arm.mkdir(exist_ok=False)
    names = ('runner.py', 'sandbox.py', 'command_driver.py', 'common.py',
             'safe_process.py', 'grade_one.py', 'grading_adapter.py',
             'college_grader.py', 'adapter.py', 'terminal_seed.json',
             'test_offline.py', 'client.py', 'capacity.py', 'worker.py',
             'accept_arm.py', 'test_capacity.py')
    originals = {}
    for name in names:
        shutil.copyfile(SOURCE / name, arm / name)
        originals[name] = sha(SOURCE / name)
    shutil.copytree(SOURCE / 'recuris', arm / 'recuris',
                   ignore=shutil.ignore_patterns('__pycache__', '.pytest_cache', '.test-tmp*'))
    # Only the task-count validation changes; resource and memory policies do not.
    capacity = arm / 'capacity.py'
    code = capacity.read_text()
    old = "assert len(protocol['tasks']) == 7 and protocol['cross_task_memory'] is False"
    assert code.count(old) == 1
    capacity.write_text(code.replace(old, "assert len(protocol['tasks']) == 20 and protocol['cross_task_memory'] is False"))
    for name in ('upstream', 'input-manifest.json'):
        (arm / name).symlink_to(BASE / name, target_is_directory=(BASE / name).is_dir())
    for name in ('jobs', 'grades', 'incoming', 'host-tmp', 'empty-tests', 'acceptance-jobs'):
        (arm / name).mkdir()
    arm_protocol = dict(protocol, experiment=arm.name)
    (arm / 'protocol.json').write_text(json.dumps(arm_protocol, indent=2))
    seed = json.loads((arm / 'terminal_seed.json').read_text())
    assert seed and not list((arm / 'jobs').iterdir()) and not list((arm / 'incoming').iterdir())
    manifest = json.loads((BASE / 'input-manifest.json').read_text())
    assert manifest['commit'] == protocol['commit']
    # Full public starter + official evaluator integrity; no evaluation output read.
    for name, expected in manifest['files'].items():
        assert sha(BASE / name) == expected, 'Pinned input changed: ' + name
    hashes = {name: sha(arm / name) for name in names}
    assert all(hashes[n] == originals[n] for n in names if n != 'capacity.py')
    provenance = {'source': str(SOURCE), 'source_ready_sha256': sha(SOURCE_ROOT / 'ready.json'),
        'source_protocol_sha256': sha(SOURCE_ROOT / 'protocol.json'),
        'source_hashes': originals, 'deployed_hashes': hashes,
        'adapter_algorithm_unchanged': True, 'author_modules_verbatim': True,
        'only_arm_code_change': 'capacity.py: expected task count 7 -> 20',
        'resource_fields_equal': RESOURCE_FIELDS,
        'task_inputs_equal': True, 'official_input_files_verified': len(manifest['files']),
        'learned_cache_copied': False, 'trial_logs_copied': False, 'model_api_calls': 0}
    (ROOT / 'source-provenance.json').write_text(json.dumps(provenance, indent=2))
    print(json.dumps({'prepared': True, 'trials': 20, 'concurrency': 6, 'paid_model_calls': 0}))


if __name__ == '__main__':
    main()
