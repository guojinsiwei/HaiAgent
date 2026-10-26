import json
import sys
from pathlib import Path
from types import SimpleNamespace
root = Path('/mnt/sdb/home/lizh639/lhtb-triple25-v161-20260926')
sys.path.insert(0, str(root / 'bestfgs-project/src'))
from bestfgs.semantic import _candidate_workspace_paths
audit = next((root / 'runs/bestfgs-modflow6-groundwater-regression-audit').glob('*/agent/audit.jsonl'))
rows = [json.loads(s) for s in audit.read_text().splitlines()]
snapshot = SimpleNamespace(location=str(root))
outcome = SimpleNamespace(parent_snapshot=snapshot, resulting_snapshot=snapshot)
for row in rows[-8:]:
    if row['event'] == 'tool_call':
        try:
            _candidate_workspace_paths(row['command']['argv'], outcome)
            print('sequence', row['seq'], 'OK')
        except OSError as error:
            print('sequence', row['seq'], 'REPRODUCED', type(error).__name__, 'errno', error.errno,
                  'reason', error.strerror)
