"""Freeze the historical comparison and the identical 20 task inputs."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent / 'longcli-dh-raw-full20-20261004'


def main():
    original = json.loads((BASE / 'protocol.json').read_text(encoding='utf-8'))
    protocol = dict(original)
    protocol.update(
        experiment=ROOT.name, created_date='2026-10-05', methods=['dsh'],
        status='preparing_not_started', source_releases={'dsh': 'official npm 0.2.0-rc.2, headless'},
        historical_comparator={'campaign': BASE.name, 'arm': 'dh', 'rerun': False,
            'protocol_sha256': hashlib.sha256((BASE / 'protocol.json').read_bytes()).hexdigest()},
        response_protocol='Official DSH native tools; no DH JSON wire or orthogonality gates',
        context_windows={'dsh': 'Official native compaction/context management',
                         'historical_dh': '48000 characters'},
        budget_definition='800 agent/request admissions including all subagents; 600 model-root tool dispatches; provider retries audited separately',
        comparison_limits=['Historical, not simultaneous randomized comparison',
                           'DSH native context management differs from DH',
                           'Native tool types differ: report shell, file, and bookkeeping counts separately'],
        fresh_container_per_task=True, fresh_home_per_task=True,
        preserved_shared_state='read-only runtime and immutable input images only',
        generation_resources={'concurrency_total': 4, 'cpu_each': 2, 'memory_gib_each': 8},
        prior_results_carried=0,
        pilot_policy='First task is included; no paid retry or automatic failed-task replay')
    path = ROOT / 'protocol.json'
    assert not path.exists(), 'Do not overwrite frozen protocol'
    path.write_text(json.dumps(protocol, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps({'tasks': len(protocol['tasks']), 'historical_arm': 'dh', 'new_arm': 'dsh'}))


if __name__ == '__main__':
    main()
