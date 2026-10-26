"""Independent accounting from checksum-verified traces; allow failed arms."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'sources/bestfgs-project/src'))
from bestfgs.lean_audit import atomic_json, read_trace


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    manifest = json.loads((ROOT/'evidence/source-manifest.json').read_text(encoding='utf-8'))
    report = json.loads((args.directory/'summary.json').read_text(encoding='utf-8'))
    observed = []
    for row in report['results']:
        events = read_trace(args.directory/(row['case']+'-'+row['arm'])/'events.jsonl')
        if events[0]['source_hashes'] != manifest['candidate']:
            raise ValueError('Different source used for live arm')
        cfg = events[0]['config']
        assert cfg['contrastive_mode'] == row['arm'] and cfg['route_search'] is False and cfg['stagnation_control'] is False
        for key, value in report['budgets'].items(): assert cfg[key] == value
        phases = [e for e in events if e['event'] == 'live_test_phase']
        assert sum(e['phase'] == 'scripted_failure_seed' for e in phases) == 2
        calls = [e for e in events if e['event'] == 'tool_call']
        wires = [e for e in events if e['event'] == 'wire_prompt' and e['role'] == 'action']
        gates = [e for e in events if e['event'] == 'contrastive_validation']
        grades = [e for e in events if e['event'] == 'independent_fixture_grade']
        assert len(calls) == row['agent_tool_calls']
        assert len(wires) == row['actual_api_usage']['api_requests']
        assert sum(e['phase'] == 'autonomous_provider' for e in phases) == row['provider_decisions']
        assert sum(not e['accepted'] for e in gates) == row['contrastive_rejections']
        assert grades[-1]['fixture_goal_verified'] == row['fixture_goal_verified']
        accepted = {e['action'].get('argv', [None])[0] for e in gates if e['accepted']}
        assert accepted.issubset({'microtool'})
        observed.append(dict(row, trace_chain_verified=True, source_hashes_verified=True,
            actual_api_prompts_verified=True,
            executed_commands_after_seed=[e['command']['argv'] for e in calls[2:]]))
    totals = {}
    for arm in ('evidence','orthogonal'):
        rows = [r for r in observed if r['arm'] == arm]
        totals[arm] = {key:sum(r[key] for r in rows) for key in ('fixture_goal_verified','submitted',
            'verified_and_submitted','agent_tool_calls','provider_decisions','contrastive_rejections',
            'autonomous_failed_calls','public_verification_passed_by_actor')}
        totals[arm]['actual_api_usage'] = {key:sum(r['actual_api_usage'].get(key,0) for r in rows)
            for key in ('api_requests','api_responses','prompt_tokens','completion_tokens','total_tokens')}
    output = dict(type='paired diagnostic pilot', totals=totals, observed_runs=observed,
        limitations=report['limitations'], statistical_or_benchmark_superiority_established=False)
    atomic_json(args.directory/'independent-analysis.json', output)
    lines = ['Contrastive exploration paired pilot (4 cases/arm; NOT benchmark evidence).',
        'Same model, thinking=false, temperature=0, memories and budgets. Threshold=0.8.',
        'The first two failed actions in each run are controlled seeds.', '',
        'case / arm / independently graded / submitted / actor verified / API requests / tools / rejections']
    for row in observed:
        lines.append(' / '.join(map(str, (row['case'],row['arm'],row['fixture_goal_verified'],row['submitted'],
            row['public_verification_passed_by_actor'],row['actual_api_usage']['api_requests'],
            row['agent_tool_calls'],row['contrastive_rejections']))))
    lines += ['', json.dumps(totals, ensure_ascii=False, indent=2), '',
              'Independent post-run grading is separate from actor-side verification.',
              'Do not treat text claims or supported prediction markers as causal proof.',
              'All result/source/trace accounting checks passed.']
    (args.directory/'RESULTS.txt').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print(json.dumps(totals, ensure_ascii=False, indent=2))


if __name__ == '__main__': main()
