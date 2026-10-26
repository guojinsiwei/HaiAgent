"""Immutable independent public fixture check; never execute generated code."""
import json
import math
from pathlib import Path

report = json.loads(Path('report.json').read_text(encoding='utf-8'))
threshold, loss = report['threshold'], report['loss']
assert type(threshold) in (int, float) and math.isfinite(threshold) and 0 < threshold <= 1
assert type(loss) in (int, float) and math.isfinite(loss) and abs(loss-threshold/2) < 1e-12
print('PARAMETER_REPORT_VALID')
