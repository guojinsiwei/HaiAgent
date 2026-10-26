"""Validate this worker's accepted files; no model/credential access."""
import argparse
import json
from common import ROOT, sha


def check(worker):
    ready = json.loads((ROOT / f'ready-{worker}.json').read_text())
    assert ready['ready'] and ready['worker'] == worker and ready['paid_api_requests'] == 0
    for name, expected in ready['hashes'].items():
        assert sha(ROOT / name) == expected, 'Accepted file changed: ' + name
    acceptance = json.loads((ROOT / ready['acceptance_file']).read_text())
    assert acceptance['state'] == 'passed' and acceptance['worker'] == worker
    assert acceptance['paid_api_requests'] == 0
    assert all(r['state'] == 'keyless_pass' and r['task_processes_stopped'] for r in acceptance['trials'])
    assert all(r['maximum_input_bytes'] <= 48000 for r in acceptance['trials'])
    assert all(r.get('actual_native_configuration_verified') for r in acceptance['trials'])
    assert all(r.get('summary_prompt_adapter_verified') for r in acceptance['trials'])
    assert any(r['root_tool_dispatches'] == 129 and r.get('native_compactions', 0) > 0
               and r.get('early_evidence_survived_and_used') and r.get('four_tool_actions_per_decision')
               and r.get('summary_exceeding_old_1024_cap_completed') for r in acceptance['trials'])
    assert any(r.get('moderate_compaction_not_per_step') and r.get('recent_raw_batch_used') and r.get('recent_file_middle_used')
               and r.get('balanced_raw_tail_preserved') for r in acceptance['trials'])
    return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--worker', type=int, required=True)
    args = parser.parse_args()
    check(args.worker)
    print(json.dumps({'state': 'accepted', 'worker': args.worker, 'paid_api_requests': 0}))
