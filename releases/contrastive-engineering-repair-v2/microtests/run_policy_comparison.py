"""Six fixed gate probes. No model, no environment commands, no success claim."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'tests'), str(ROOT/'sources/bestfgs-project/src')]
from bestfgs.lean_audit import atomic_json
from test_contrastive_exploration import (anchor, evidence_action, orthogonal_action,
    check_evidence, validate_orthogonal, run_action)


def main():
    check = run_action('python', 'check.py', 'config.json')
    shell = run_action('bash', '-lc', 'python check.py config.json')
    old_parameter = run_action('python', 'train.py', '--batch', '2')
    cases = [
        dict(name='unchanged_repeat', old=check, new=check, expected_allow=False, options={}),
        dict(name='shell_spacing_rewrite', old=shell,
             new=run_action('bash','-lc',' python  "check.py"  config.json '), expected_allow=False, options={}),
        dict(name='meaningful_numeric_parameter', old=old_parameter,
             new=run_action('python','train.py','--batch','1'), expected_allow=True, options={}),
        dict(name='verification_after_relevant_change', old=check, new=check, expected_allow=True,
             options=dict(kind='retry', changed_paths=['config.json']), deps={'config.json':'file:new'}),
        dict(name='irrelevant_change', old=check, new=check, expected_allow=False,
             options=dict(kind='retry', changed_paths=['notes.txt']),
             deps={'config.json':'file:old','notes.txt':'file:new'}),
        dict(name='new_discriminating_probe', old=check, new=run_action('cat','environment.txt'),
             expected_allow=True, options={})]
    rows = []
    for case in cases:
        anchors = [anchor(case['old'])]
        a_audit, a_reason = check_evidence(evidence_action(case['new'], **case['options']), anchors, case.get('deps'))
        b_audit, b_reason = validate_orthogonal(orthogonal_action(case['new']), anchors, .8)
        rows.append(dict(case=case['name'], expected_allow=case['expected_allow'],
            evidence_allowed=a_reason is None, orthogonal_allowed=b_reason is None,
            evidence_reason=a_reason, orthogonal_reason=b_reason,
            orthogonal_similarity=b_audit['max_similarity'],
            evidence_correct=(a_reason is None) == case['expected_allow'],
            orthogonal_correct=(b_reason is None) == case['expected_allow']))
    report = dict(type='deterministic gate-only probes, no LLM or CLI execution', threshold=.8,
        cases=rows, evidence_correct=sum(r['evidence_correct'] for r in rows),
        orthogonal_correct=sum(r['orthogonal_correct'] for r in rows), api_calls=0,
        does_not_prove_autonomous_exploration_or_task_gain=True)
    atomic_json(ROOT/'evidence/policy-comparison.json', report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__': main()
