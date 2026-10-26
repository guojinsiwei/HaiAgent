"""Run unchanged Scheme official test script on direct and round-tripped sources.

No model calls, credentials, host mounts, or reference solution use.
Containers are retained stopped for audit, labelled and uniquely named.
"""
import ast
import argparse
import json
import logging
from pathlib import Path
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument('--cpp', action='store_true')
parser.add_argument('--archive')
parser.add_argument('--label', default='fixture')
options = parser.parse_args()
task_id = 'cmu15_445_p0' if options.cpp else 'cs61_fa24_scheme'
project = 'cmu15_445' if options.cpp else 'cs61_fa24_scheme'
image = 'longcli-audit/c-env:2015f37' if options.cpp else 'longcli-audit/make-pytest:2015f37'
test_timeout = 720 if options.cpp else 300
TASK = ROOT / 'upstream/tasks_long_cli' / task_id
OUT = ROOT / ('replay-' + task_id + '-' + time.strftime('%Y%m%d-%H%M%S'))
OUT.mkdir()

def docker(*args, check=True):
    p = subprocess.run(['docker', *map(str, args)], capture_output=True, text=True,
                       encoding='utf-8', errors='replace', timeout=120)
    if check and p.returncode:
        raise RuntimeError(p.stderr[-3000:])
    return p

# Load the actual upstream metric helper, not the no-op LongCliParser success flag.
harness = ROOT / 'upstream/terminal_bench/harness/harness.py'
tree = ast.parse(harness.read_text(encoding='utf-8'))
func = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
            and n.name == '_compute_pytest_metrics_from_content')
sys.path.insert(0, str(ROOT / 'upstream'))
namespace = {'logger': logging.getLogger('longcli-probe')}
for filename in ['base_parser.py', 'pytest_parser.py']:
    path = ROOT / 'upstream/terminal_bench/parsers' / filename
    parsed = ast.parse(path.read_text())
    parsed.body = [n for n in parsed.body if not (isinstance(n, ast.ImportFrom)
                   and (n.module or '').startswith('terminal_bench'))]
    exec(compile(parsed, str(path), 'exec'), namespace)
rounder = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == '_round_sig')
exec(compile(ast.Module(body=[rounder, func], type_ignores=[]), str(harness), 'exec'), namespace)
assert namespace['_compute_pytest_metrics_from_content']('=== short test summary info ===\nPASSED test_sample.py::test_ok\nFAILED test_sample.py::test_bad')[0:2] == (0, 0.5)

results = []
cases = [(options.label, options.archive)] if options.archive else [('direct', 'cube-inputs-v1.tar.gz'), ('returned', 'returned-source.tar.gz')]
for mode, archive in cases:
    dest = OUT / mode
    dest.mkdir()
    name = 'longcli-probe-' + mode + '-' + uuid.uuid4().hex[:8]
    docker('run', '-d', '--name', name, '--label', 'purpose=longcli-portability-probe',
           '--cpuset-cpus', '0,1', '--memory', '4g', '-e', 'TEST_DIR=/tests',
           '-w', '/app', image, 'sleep', 'infinity')
    try:
        docker('cp', ROOT / archive, name + ':/tmp/source.tar.gz')
        docker('exec', name, 'tar', '-xzf', '/tmp/source.tar.gz', '-C', '/app', project)
        docker('cp', TASK / 'INSTRUCTION.md', name + ':/app/INSTRUCTION.md')
        docker('cp', TASK / 'tests', name + ':/tests')
        docker('cp', TASK / 'run-tests.sh', name + ':/tests/run-tests.sh')
        with (dest / 'console.log').open('w', encoding='utf-8') as log:
            p = subprocess.run(['docker', 'exec', name, 'timeout', str(test_timeout), 'bash', '/tests/run-tests.sh'],
                               stdout=log, stderr=subprocess.STDOUT, timeout=test_timeout+30)
        docker('cp', name + ':/app/test_output', dest)
        score = json.loads((dest / 'test_output/f2p_score.json').read_text())
        content = (dest / 'test_output/p2p_output.txt').read_text(errors='replace')
        p2p = namespace['_compute_pytest_metrics_from_content'](content)
        assert p2p[2], 'No P2P tests parsed: infrastructure failure, not a valid zero score'
        results.append({'mode': mode, 'container': name, 'script_exit': p.returncode,
                        'f2p': score, 'p2p': p2p})
        print(json.dumps({'mode': mode, 'script_exit': p.returncode, 'f2p': score,
                          'p2p_pass': p2p[0], 'p2p_score': p2p[1], 'p2p_count': len(p2p[2])}), flush=True)
    finally:
        docker('stop', '-t', '5', name, check=False)
        (OUT / 'result.json').write_text(json.dumps(results, indent=2))
if len(results) == 2:
    equal = all(results[0][k] == results[1][k] for k in ['script_exit', 'f2p', 'p2p'])
    print(json.dumps({'equal_metrics': equal, 'report': str(OUT), 'model_calls': 0}), flush=True)
    assert equal
