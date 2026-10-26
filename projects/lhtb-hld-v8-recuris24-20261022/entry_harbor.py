"""Use the frozen official LHTB Harbor in this experiment only."""
import os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'vendor-src'))
from harbor.trial.trial import Trial
original=Trial._execute_agent
async def run_agent(self):
    if os.environ.get('LHTB_OFFLINE')=='1' and os.environ.get('ENTRY_CONTINUATION_TEST')!='1':self._task.config.agent.continue_until_timeout=False
    return await original(self)
Trial._execute_agent=run_agent
if __name__=='__main__':
    from harbor.cli.main import app
    sys.exit(app())
