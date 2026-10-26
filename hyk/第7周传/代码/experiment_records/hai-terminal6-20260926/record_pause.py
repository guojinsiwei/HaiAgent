"""Record an already applied user-requested pause; does not signal or resume anything."""
import json
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / 'project/src'))
from haiagent.storage import atomic_json

health = json.loads((HERE / 'health.json').read_text())
assert health['pid'] == 4101828 and health['child_pid'] == 4102063
assert not Path('/proc/4101828').exists(), 'Scheduler still alive'
container = json.loads(subprocess.check_output(['docker', 'inspect', 'a622da91e2f3']))[0]
assert container['Name'] == '/path-tracing__efop2na__env-main-1'
assert not container['State']['Running'], 'Task container is still running'
assert not Path('/proc/4102063').exists(), 'Harbor process still alive'
pause = {'state': 'paused_by_user', 'paused_at': time.time(),
         'reason': 'High action JSON format-error rate; user explicitly approved pause',
         'scheduler_stopped': True, 'harbor_pid': 4102063, 'harbor_stopped': True,
         'container_id': container['Id'], 'container_stopped': True, 'container_retained': True,
         'automatic_resume': False, 'prior_health': health,
         'warning': 'Frozen task clocks do not reset. Do not resume as an uninterrupted comparable trial.'}
if (HERE / 'pause.json').exists():
    raise RuntimeError('Pause record already exists')
atomic_json(HERE / 'pause.json', pause)
atomic_json(HERE / 'health.json', health | {'state': 'paused_by_user', 'heartbeat': pause['paused_at'],
                                         'scheduler_stopped': True, 'container_stopped': True})
print(json.dumps({k: v for k, v in pause.items() if k != 'prior_health'}))
