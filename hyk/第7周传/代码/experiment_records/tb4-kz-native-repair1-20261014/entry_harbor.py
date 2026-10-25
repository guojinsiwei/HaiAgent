import sys
from pathlib import Path
BASE='/var/tmp/lizh639-tb4-kz-dsh-unlimited-repair-20261014'
sys.path.append(BASE)
from harbor.trial.trial import Trial
original=Trial._compute_agent_timeout_sec
def timeout(self):
    if self.config.agent.import_path in ('harbor_pair:PairAgent','harbor_legacy:LegacyAgent'):return None
    return original(self)
if __name__=='__main__':
    Trial._compute_agent_timeout_sec=timeout
    from harbor.cli.main import app
    sys.exit(app())
