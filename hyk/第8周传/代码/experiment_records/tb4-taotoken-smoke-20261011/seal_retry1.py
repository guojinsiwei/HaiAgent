"""Seal verified, credential-free acceptance inputs before the paid retry."""
import datetime
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parent
trial = root / 'jobs/retry1-offline-acceptance/wal-recovery-ordering__Z2dxSfA'
result = json.loads((trial / 'result.json').read_text())
checks = json.loads((trial / 'agent/offline-checks-wire.json').read_text())
preflight = json.loads((root / 'preflight.json').read_text())
assert result['exception_info'] is None and result['finished_at']
assert checks['exit_code'] == 0
assert all(checks[k] for k in ('native_tool_result', 'settings_ok', 'kz_tool_present', 'wire_integrity'))
assert checks['wire_requests'] == checks['calls'] == 3
assert preflight['oracle_reward'] == 1 and preflight['ready_for_new_key']
names = ['route-audit.mjs', 'dsh_runtime.py', 'container-retry1.py',
         'harbor_retry1.py', 'harbor_kz.py', 'offline_headless.py',
         'route.patch.yml', 'runtime.tar.gz', 'launch_retry1.py']
record = {
    'sealed_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'offline_passed': True, 'live_api_test_pending': True,
    'checks': checks, 'oracle_reward': preflight['oracle_reward'],
    'sha256': {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in names},
}
(root / 'retry1-ready.json').write_text(json.dumps(record, indent=2))
print(json.dumps(record, indent=2))
