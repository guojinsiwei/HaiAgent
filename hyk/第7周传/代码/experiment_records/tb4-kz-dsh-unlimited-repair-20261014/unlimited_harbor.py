"""Campaign-local Harbor entry point; do not alter task files or installed Harbor.

Only this campaign's two solver classes lose the agent wall timeout. Official
environment build, installation and verifier timeouts remain unchanged.
"""
import sys
from harbor.trial.trial import Trial
ORIGINAL = Trial._compute_agent_timeout_sec

def solver_timeout(self):
    if self.config.agent.import_path in ('harbor_pair:PairAgent','harbor_pair:KZAgent'):
        return None
    return ORIGINAL(self)

def main():
    Trial._compute_agent_timeout_sec=solver_timeout
    from harbor.cli.main import app
    sys.exit(app())

if __name__=='__main__':main()
