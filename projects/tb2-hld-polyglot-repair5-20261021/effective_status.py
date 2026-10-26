"""Read-only combined report for original batch and both finite repair batches."""
from pathlib import Path
import importlib.util
import json

R = Path(__file__).resolve().parent
MAIN = R.parent / 'tb2-hld-recuris39-20261021'
OTHER = R.parent / 'tb2-hld-recuris39-repair4-20261021'


def build():
    main = json.loads((MAIN/'health.json').read_text())
    retry = json.loads((R/'health.json').read_text()) if (R/'health.json').exists() else {}
    replacements = {r['original_job']:r for r in retry.get('rows', [])}
    for row in main['rows']:
        if row['job'] in replacements:
            updated = replacements[row['job']]
            row['original_result'] = row.get('result')
            row['result'] = updated.get('result', {})
            row['state'] = updated['state']
            row['repair_job'] = updated['job']
    spec = importlib.util.spec_from_file_location('prior_repairs', OTHER/'effective_status.py')
    prior = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(prior)
    result = prior.build(main)
    result['polyglot_repair'] = {k:retry.get(k) for k in ['state','updated','rows','active']}
    return result


if __name__ == '__main__':
    print(json.dumps(build(), indent=2))
