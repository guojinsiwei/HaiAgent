"""Read-only overlay: keep first attempts and expose scoring/retry provenance."""
from pathlib import Path
import copy
import json

R = Path(__file__).resolve().parent
ORIGINAL = R.parent/'tb2-hld-recuris39-20261021'


def read(path):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return {}


def build(main=None):
    main = read(ORIGINAL/'health.json') if main is None else main
    rows = copy.deepcopy(main.get('rows', []))
    repair = read(R/'health.json')
    preflight = read(R/'preflight-status.json')
    saved = read(R/'feal-score/result.json')
    replacements = {r['original_job']:r for r in repair.get('rows', [])}
    for row in rows:
        if row['job'] in replacements:
            retry = replacements[row['job']]
            row['original_result'] = row.get('result')
            row['state'] = retry['state']
            row['result'] = retry.get('result', {})
            row['repair_job'] = retry['job']
        elif row['job'] == 'tb2hr39-13-recuris-feal-linear-cryptanalysis' and saved.get('engineering_clean'):
            row['original_result'] = row.get('result')
            row['result'] = saved
            row['state'] = 'scored_saved_submission'
    summary = {}
    for arm in ['hld', 'recuris']:
        selected = [r for r in rows if r['arm'] == arm]
        scored = [r for r in selected if r.get('result', {}).get('reward') in (0, 1)]
        summary[arm] = dict(total=len(selected), scored=len(scored),
            passed=sum(r['result']['reward'] == 1 for r in scored),
            running=sum(r['state'] == 'running' for r in selected),
            pending=sum(r['state'] == 'pending' for r in selected),
            unresolved_engineering=sum(r['state'] == 'engineering_failure' for r in selected))
    return dict(effective_summary=summary, repair_state=repair.get('state'),
        repair_active=repair.get('active', []),
        repair_rows=[{k:r.get(k) for k in ['task','arm','state','job','budget_job','result']}
                     for r in repair.get('rows', [])],
        preflight_passed=preflight.get('passed'),
        feal_saved_score={k:saved.get(k) for k in ['engineering_clean','reward','paid_calls','solver_rerun']},
        first_attempt_summary=main.get('summary'), budget=main.get('spending'))


if __name__ == '__main__':
    print(json.dumps(build(), indent=2))
