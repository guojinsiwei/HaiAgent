"""Real filesystem, scripted models: repeated failure -> advice -> restore -> submit."""
import argparse
import json
from pathlib import Path
import sys

from bestfgs.lean_audit import read_trace
from bestfgs.lean_environment import LiveWorkspace
from bestfgs.lean_protocol import LeanConfig
from bestfgs.lean_runtime import LeanTaskRunner
from bestfgs.models import TaskSpec


class Scripted:
    def __init__(self, values): self.values=iter(values)
    def complete_json(self, **kwargs): return next(self.values)


def command(code, **kwargs):
    return dict(action='run',argv=[sys.executable,'-c',code],purpose='offline demonstration',**kwargs)


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); root=args.output.resolve(); root.mkdir(parents=True,exist_ok=False)
    seed=root/'seed'; seed.mkdir(); (seed/'input.txt').write_text('correct input',encoding='utf-8')
    fail=command("from pathlib import Path; print(Path('missing.txt').read_text())")
    memory=dict(conclusion='The available input is input.txt, not missing.txt',
                condition='for this unchanged task input',evidence_ids=['E4'])
    actor=Scripted([fail,fail,fail,
        command("from pathlib import Path; print(sorted(p.name for p in Path('.').iterdir()))"),
        command("from pathlib import Path; Path('answer.txt').write_text(Path('input.txt').read_text())",memory=memory),
        dict(action='checkpoint',label='working artifact',hypothesis='Preserve the correct copy'),
        command("from pathlib import Path; Path('answer.txt').write_text('bad experiment')"),
        dict(action='restore',checkpoint_id='C2',reason='The experimental change damaged the answer'),
        dict(action='submit',summary='Restored the working file',uses_memory=['M1'])])
    advisor=Scripted([dict(alternatives=[dict(hypothesis='The source filename may be wrong',
        check='List the existing input filenames',difference='Inspect actual files instead of repeating the failed open',
        evidence_ids=['E3'])])])
    env=LiveWorkspace(seed,root/'environment')
    result=LeanTaskRunner(env,actor,advisor,LeanConfig(max_turns=20,max_tools=12),root/'audit').run(
        TaskSpec('offline-demo','Read the available input and deliver answer.txt'))
    assert (env.workspace/'answer.txt').read_text()=='correct input'
    assert result['submitted'] and result['advisor_rounds']==1
    assert result['mechanism_utilization']['branch_restores']==1
    assert not (seed/'answer.txt').exists()
    trace=read_trace(root/'audit/events.jsonl')
    print(json.dumps(dict(offline=True,paid_api_calls=0,audit_verified=len(trace),
                         answer=(env.workspace/'answer.txt').read_text(),result=result),indent=2))


if __name__=='__main__': main()
