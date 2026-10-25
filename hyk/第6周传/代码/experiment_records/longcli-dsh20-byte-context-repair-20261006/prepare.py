"""Clean protocol and keyless acceptance; no credentials or paid calls."""
import argparse
import json
from pathlib import Path
from common import ROOT, save, sha


def prepare(worker, revision):
    from runner import BASE, run_trial
    assert not list(ROOT.glob('launch-*.claim')), 'Never modify a launched campaign'
    acceptance_name = f'acceptance-{worker}-r{revision}.json'
    assert not (ROOT / acceptance_name).exists(), 'Never overwrite worker acceptance'
    previous = json.loads((BASE / 'protocol.json').read_text())
    protocol = {k: previous[k] for k in ('commit', 'tasks', 'model', 'thinking', 'temperature', 'grading_resources', 'generation_resources')}
    protocol.update(experiment=ROOT.name, methods=['dsh'], total_trials=20,
                    max_turns=800, max_tools=600, max_tokens=4096, input_bytes=48000,
                    native_catalog_context_tokens=1000000, wire_attempt_ceiling=1600, retries_per_decision=1,
                    output_bytes=24000, command_seconds=300, runtime_version='0.2.0-rc.2',
                    prior_results_preserved=True, automatic_task_retry=False,
                    baseline_label='Official DSH 0.2.0-rc.2 + byte-context budget adapter v2 (modified context adaptation)',
                    summary_prompt_adapter={'scope': 'final native compaction user instruction only',
                        'target_words': 180, 'maximum_requested_words': 300,
                        'maximum_requested_summary_bytes': 2500, 'input_bytes_charged': True,
                        'directive_replaced_not_appended': True,
                        'solver_prompt_changed': False, 'hard_output_cap_changed': False,
                        'history_removed_at_provider': False, 'additional_retries': 0},
                    input_unit_note='DSH UTF-8 messages+native-tools <=48000; RAW historical byte limit; DH historical character limit. Not identical token budgets.',
                    native_interface_note='Native DSH tools and recovery retained, not converted to DH JSON. DSH counts root native tools including file/goal operations.',
                    context_adapter='Budget extension gates pressure on conservative projected UTF-8 envelope >=42000 bytes; preserves >=4096-byte balanced raw tail and >=5000-byte useful prefix; native pruning limited to older results unless fixed+recent raw+checkpoint reserve alone is >=48000 bytes, with audited irreducible-latest-group fallback; one native compactRegion transaction per boundary. Native commit/shrink/replay unchanged. Exact provider 48000-byte guard authoritative; no hidden history removal.',
                    runtime_difference='Native DSH keeps a session process; DH/RAW start a new isolated process per command. Same frozen task rootfs and toolchain, not identical process semantics.')
    if (ROOT / 'protocol.json').exists():
        if json.loads((ROOT / 'protocol.json').read_text()) != protocol:
            assert revision > 1, 'Shared campaign protocol differs'
            archive = ROOT / ('protocol-pre-r' + str(revision) + '.json')
            if not archive.exists():
                save(archive, json.loads((ROOT / 'protocol.json').read_text()))
            save(ROOT / 'protocol.json', protocol)
    else:
        save(ROOT / 'protocol.json', protocol)
    resources = json.loads((BASE / f'resources-{worker}.json').read_text())
    row = previous['tasks'][0]
    trials = [run_trial(row, resources['cpu_slots'][0], mock=True, suffix=f'-worker{worker}-r{revision}-a'),
              run_trial(row, resources['cpu_slots'][0], mock=True, suffix=f'-worker{worker}-r{revision}-b', pressure_steps=32),
              run_trial(row, resources['cpu_slots'][0], mock=True, suffix=f'-worker{worker}-r{revision}-c', pressure_steps=48, pressure_rows=8)]
    passed = all(r['state'] == 'keyless_pass' for r in trials)
    save(ROOT / acceptance_name, {'state': 'passed' if passed else 'failed', 'trials': trials,
                                           'paid_api_requests': 0, 'worker': worker})
    if not passed:
        print(json.dumps({'state': 'failed', 'trials': trials}))
        raise SystemExit(1)
    names = ['protocol.json', 'budget.mjs', 'byte_compaction.mjs', 'experiment.patch.yml', 'runner.py', 'provider.py', 'context_limit.py', 'summary_prompt.py',
             'isolated_entry.py', 'launch.py', 'device_setup.py', 'common.py', 'check_ready.py', 'prepare.py', acceptance_name]
    save(ROOT / f'ready-{worker}.json', {'ready': True, 'worker': worker, 'paid_api_requests': 0,
                              'acceptance_file': acceptance_name,
                              'hashes': {name: sha(ROOT / name) for name in names}})
    print(json.dumps({'state': 'ready_not_started', 'worker': worker, 'keyless_trials': 3, 'paid_api_requests': 0}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--worker', type=int, required=True)
    parser.add_argument('--revision', type=int, default=1)
    args = parser.parse_args()
    prepare(args.worker, args.revision)
