"""Freeze a selected context budget after rerunning keyless native integration."""
import argparse
import json
from pathlib import Path
import subprocess

from common import ROOT, save, sha


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--context-window', type=int, choices=(16384, 1000000), default=16384)
    args = parser.parse_args()
    assert not (ROOT / 'launch.claim').exists(), 'Already launched; configuration is immutable'
    assert not list((ROOT / 'jobs').iterdir()), 'Existing jobs must not be overwritten'
    base_patch = (ROOT / 'experiment.base.patch.yml').read_text()
    assert 'contextWindow: 1000000' in base_patch
    patch = base_patch.replace('contextWindow: 1000000', 'contextWindow: ' + str(args.context_window))
    patch += '\n- id: compaction-basic\n  config:\n    headroomTokens: 1024\n    maxTokens: 2048\n'
    (ROOT / 'experiment.patch.yml').write_text(patch)
    protocol = json.loads((ROOT / 'protocol.json').read_text())
    protocol.update(status='ready_not_started',
        context_windows={'dsh': {'tokens': args.context_window, 'management': 'official native compaction'},
                         'historical_dh': {'characters': 48000}},
        budget_definition='800 total provider streams/attempts, including title, compaction, retries and subagents; 600 model-root native tool dispatches; 7200 seconds',
        context_comparison_note='16384 tokens is an approximate English-input budget match, not exact equivalence to 48000 characters; tool schemas also consume DSH context',
        retry_comparison_note='DSH hard 800 ceiling includes retries; historical DH 800 logical requests allowed separately counted wire retries',
        execution_comparison_note='DSH solves in new academy Docker containers; historical DH solved in CubeStudio private chroots from the same pinned toolchain exports. This is a historical practical comparison, not a single-factor ablation.',
        context_selection=args.context_window,
        automatic_failed_task_retry=False)
    save(ROOT / 'protocol.json', protocol)
    subprocess.run([str(ROOT / 'runtime/node/package/bin/node'), str(ROOT / 'test_budget.mjs')], check=True, timeout=60)
    subprocess.run(['/mnt/sdb/home/lizh639/terminalbench-v14-setup/runtime/bin/python', '-B',
                    str(ROOT / 'runner.py'), '--keyless'], check=True, timeout=300)
    acceptance = json.loads((ROOT / 'environment-acceptance.json').read_text())
    assert acceptance['state'] == 'passed' and len(acceptance['tasks']) == 20
    filenames = ['runner.py', 'launch.py', 'budget.mjs', 'experiment.patch.yml', 'protocol.json',
                 'common.py', 'college_grader.py', 'input-manifest.json', 'test_budget.mjs', 'validate.py',
                 'return_artifacts.py',
                 'runtime/dsh/package-lock.json', 'runtime/dsh/node_modules/@deepseek-ai/dsh/lib/bin.js',
                 'runtime/dsh/node_modules/@deepseek-ai/dsh-base/cordis.patch.yml',
                 'runtime/node/package/bin/node']
    save(ROOT / 'deployment-manifest.json', {'state': 'ready_not_started', 'official_dsh_version': '0.2.0-rc.2',
        'files': {name: sha(ROOT / name) for name in filenames}, 'paid_api_requests': 0})
    print(json.dumps({'state': 'ready_not_started', 'context_tokens': args.context_window,
                      'tasks': 20, 'concurrency': 4, 'paid_api_requests': 0}))


if __name__ == '__main__':
    main()
