"""Prepare a separately identified rerun; preserve the original campaign verbatim."""
import json
import hashlib
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent
OLD = Path('/var/tmp/lizh639-longcli-dsh20-20261005')


def save(path, value):
    path.write_text(json.dumps(value, indent=2))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert ROOT.name == 'lizh639-longcli-dsh20-repair1-20261005'
    assert not (ROOT / 'launch.claim').exists()
    assert not (ROOT / 'protocol.json').exists(), 'Never overwrite an initialized campaign'
    old = json.loads((OLD / 'health.json').read_text())
    assert len(old['generation_done']) == 20 and not old['active'], 'Old generation still active'
    for name in ('common.py', 'college_grader.py', 'input-manifest.json'):
        shutil.copyfile(OLD / name, ROOT / name)
    for name in ('runtime', 'upstream'):
        (ROOT / name).symlink_to((OLD / name).resolve(), target_is_directory=True)
    for name in ('empty-tests', 'jobs'):
        (ROOT / name).mkdir()
    shutil.copyfile(OLD / 'installation.json', ROOT / 'installation.json')
    protocol = json.loads((OLD / 'protocol.json').read_text())
    protocol.update(experiment='longcli-dsh20-repair1-20261005', status='preflight_not_started',
        rerun_of=OLD.name, source_results_preserved=True, automatic_failed_task_retry=False,
        context_selection=1000000,
        context_windows={'dsh': {'tokens': 1000000, 'management': 'official native compaction'},
                         'historical_dh': {'characters': 48000}},
        context_comparison_note='DSH uses the official model 1M context capacity, NOT a matched 16K window. Historical DH uses 48000 characters. This is a practical comparison, NOT an equal-context single-factor ablation.',
        changes=['restore accurate 1M adapter context capacity', 'restore native compaction headroom',
                 'capture native finish reason and provider finish reasons', 'pause admissions on native failures',
                 '32-step long-context regression plus first real task pilot'],
        unchanged={'model': 'deepseek-flash', 'temperature': 0, 'thinking': 'disabled',
                   'api_attempts_per_task': 800, 'root_tools_per_task': 600, 'wall_seconds': 7200,
                   'output_tokens_per_call': 4096, 'solver_concurrency_after_pilot': 4})
    save(ROOT / 'protocol.json', protocol)
    patch = (OLD / 'experiment.base.patch.yml').read_text()
    assert 'contextWindow: 1000000' in patch and 'compaction-basic' not in patch
    # The native 65536 headroom now fits the true model window. Retain a 2048
    # summary cap instead of accidentally permitting 65536-token summaries.
    patch += '\n- id: compaction-basic\n  config:\n    headroomTokens: 65536\n    maxTokens: 2048\n'
    (ROOT / 'experiment.patch.yml').write_text(patch)
    save(ROOT / 'repair-provenance.json', {'old_campaign': str(OLD), 'original_manifest_sha256': sha(OLD / 'deployment-manifest.json'),
        'runtime_reused_readonly': True, 'new_task_homes': True, 'old_results_modified': False,
        'paid_api_requests': 0})
    print(json.dumps({'state': 'repair_prepared', 'old_results_preserved': True, 'paid_api_requests': 0}))


if __name__ == '__main__':
    main()
