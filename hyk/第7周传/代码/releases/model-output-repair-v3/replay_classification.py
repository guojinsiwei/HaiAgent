"""Reclassify recorded metadata into a NEW report, retaining old scores and labels."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT/'integration'), str(ROOT/'sources')]
from outcomes import classify

evidence = json.loads((ROOT/'evidence/recorded-errors.json').read_text())
rows = []
for item in evidence['records']:
    classified = classify(item['result'], item['events'])
    rows.append(dict(task=item['task'], reward=item['result']['verifier_result']['rewards']['reward'],
        original_classification=item['original_classification'], corrected_classification=classified,
        original_audit_sha256=item['audit_sha256'], inner_error_codes=[e['error_code'] for e in item['inner_errors']]))
by_task = {row['task']:row for row in rows}
for task in ('modflow6-groundwater-regression-audit', 'foldseek-paper-reproduction'):
    assert by_task[task]['corrected_classification']['recovered_model_errors'] == 3
    assert by_task[task]['corrected_classification']['method_issues'] == []
for task in ('gdal-proj-raster-regression', 'great-expectations-audit'):
    assert by_task[task]['corrected_classification']['method_issues'] == ['model_error']
assert sum(bool(row['corrected_classification']['method_issues']) for row in rows) == 2
report = dict(scope='Offline classification replay only, not a rerun or modified official score', rows=rows,
    before_method_issue_trials=sum(bool(r['original_classification']['method_issues']) for r in rows),
    after_method_issue_trials=sum(bool(r['corrected_classification']['method_issues']) for r in rows))
(ROOT/'evidence/classification-replay.json').write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))
