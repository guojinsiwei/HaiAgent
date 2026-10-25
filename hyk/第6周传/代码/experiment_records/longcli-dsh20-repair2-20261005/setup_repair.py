"""Prepare uniform20 rerun with native output allowance; never overwrite previous runs."""
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent
PREVIOUS = Path('/var/tmp/lizh639-longcli-dsh20-repair1-20261005')


def save(path, value):
    path.write_text(json.dumps(value, indent=2))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert ROOT.name == 'lizh639-longcli-dsh20-repair2-20261005'
    assert not (ROOT / 'protocol.json').exists(), 'Never overwrite an initialized campaign'
    health = json.loads((PREVIOUS / 'health.json').read_text())
    assert not health['active'], 'Previous solver tasks still active'
    for name in ('common.py', 'college_grader.py', 'input-manifest.json', 'installation.json'):
        shutil.copyfile(PREVIOUS / name, ROOT / name)
    for name in ('runtime', 'upstream'):
        (ROOT / name).symlink_to((PREVIOUS / name).resolve(), target_is_directory=True)
    for name in ('empty-tests', 'jobs'):
        (ROOT / name).mkdir()
    protocol = json.loads((PREVIOUS / 'protocol.json').read_text())
    protocol.update(experiment='longcli-dsh20-repair2-20261005', status='preflight_not_started',
        rerun_of=PREVIOUS.name, source_results_preserved=True, automatic_failed_task_retry=False,
        task_result_selection='All20 fresh tasks, uniform output allowance; no cherry-picked result replacement.',
        changes=['restore official pi-ai default maxTokens=32768 at config, plugin and relay layers',
                 'native large-write fixture with failing4096 control', 'start with previously truncated CMU P1 pilot'],
        unchanged={'model': 'deepseek-flash', 'temperature': 0, 'thinking': 'disabled',
                   'api_attempts_per_task': 800, 'root_tools_per_task': 600, 'wall_seconds': 7200,
                   'context_tokens': 1000000, 'solver_concurrency_after_pilot': 4},
        output_tokens_per_call=32768,
        output_comparison_note='Single-response allowance increased4096->32768 (official pi-ai default). Historical DH used4096; report this difference. No total token spending ceiling was previously defined.',
        decision_logic_modified=False, repetition_intervention_added=False)
    tasks = protocol['tasks']
    protocol['tasks'] = [r for r in tasks if r['task'] == 'cmu15_445_p1'] + [r for r in tasks if r['task'] != 'cmu15_445_p1']
    assert len(protocol['tasks']) == 20 and len({r['task'] for r in protocol['tasks']}) == 20
    save(ROOT / 'protocol.json', protocol)
    legacy = (PREVIOUS / 'experiment.patch.yml').read_text()
    assert legacy.count('maxTokens: 4096') == 1 and legacy.count('defaultMaxTokens: 4096') == 1
    patch = legacy.replace('maxTokens: 4096', 'maxTokens: 32768').replace('defaultMaxTokens: 4096', 'defaultMaxTokens: 32768')
    (ROOT / 'experiment.patch.yml').write_text(patch)
    (ROOT / 'legacy-output.patch.yml').write_text(legacy)
    shutil.copyfile(PREVIOUS / 'budget.mjs', ROOT / 'legacy-budget.mjs')
    save(ROOT / 'repair-provenance.json', {'previous_campaign': str(PREVIOUS),
        'previous_manifest_sha256': sha(PREVIOUS / 'deployment-manifest.json'), 'previous_results_modified': False,
        'runtime_reused_readonly': True, 'paid_api_requests': 0,
        'failure_evidence': {'cmu15_445_p0': {'finish_reason': 'length', 'completion_tokens': 4096, 'truncated_tool': 'write'},
                             'cmu15_445_p1': {'finish_reason': 'length', 'completion_tokens': 4096, 'truncated_tool': 'write'}}})
    print(json.dumps({'state': 'repair_prepared', 'tasks': 20, 'pilot': 'cmu15_445_p1', 'output_tokens': 32768,
                      'previous_results_preserved': True, 'paid_api_requests': 0}))


if __name__ == '__main__':
    main()
