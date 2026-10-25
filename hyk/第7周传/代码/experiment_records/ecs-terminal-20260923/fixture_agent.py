"""Synthetic scripted client, used only in infrastructure tests, never formal jobs."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys

from bestfgs.__main__ import build_parser
from bestfgs.evidence_runtime import run_from_args
from container_runner import deliver


class FakeClient:
    def __init__(self, config, **kwargs):
        self.turn = 0

    def complete_json(self, **kwargs):
        self.turn += 1
        code = ["raise SystemExit(1)", "from pathlib import Path; Path('fixture-old').unlink(); Path('fixture-answer').write_text('ok')"]
        if self.turn <= 2:
            return {'done':False,'commands':[{'argv':[sys.executable,'-c',code[self.turn-1]],'description':'synthetic infrastructure test'}]}
        return {'done':True}

    def usage_summary(self):
        return {'model_calls':self.turn,'api_requests':0}


method = sys.argv[1]
root = Path('/tmp/synthetic-agent')
Path('/app/fixture-old').write_text('old')
parser = build_parser()
args = parser.parse_args(['--goal','Synthetic test only: write fixture-answer and delete fixture-old',
                          '--workspace','/app','--run-root',str(root),'--model','fixture-no-network',
                          '--provider','deepseek','--max-iterations','3','--max-tool-calls','4',
                          '--comparison-metrics','--no-adaptive-budget','--success-judge-mode','off'])
with redirect_stdout(io.StringIO()) as output:
    code = run_from_args(args,parser,raw=method=='raw',client_factory=FakeClient)
assert code == 1
result = json.loads(output.getvalue())
assert result['decision_turns'] == 3
assert result['comparison_metrics']['interaction_rounds'] == 2
assert result['comparison_metrics']['tool_calls'] == 2
assert result['blocking_memory_mode'] == ('off' if method=='raw' else 'control')
deliver(Path(result['best_workspace']),root/'root',Path('/app'))
assert not Path('/app/fixture-old').exists()
assert Path('/app/fixture-answer').read_text() == 'ok'
print(json.dumps({'method':method,'decision_turns':3,'interaction_rounds':2,'cli_calls':2,
                  'api_requests':0,'delete_delivery':True,'passed':True}))
