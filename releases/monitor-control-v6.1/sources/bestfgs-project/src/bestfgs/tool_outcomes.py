"""Separate process exit, observed warnings and explicit public checks."""
import re
from pathlib import PurePath


def assess(result):
    observation = getattr(result, 'execution_observation', None) or {}
    combined = result.stdout + '\n' + result.stderr
    # Text is untrusted: warnings prompt inspection, never a hard ban or success.
    traceback_signal = bool(re.search(r'(?m)^Traceback \(most recent call last\):', combined)
                             and re.search(r'(?m)^[\w.]+(?:Error|Exception):', combined))
    stage_failure = bool(observation.get('nonzero_statuses'))
    process_ok = result.succeeded
    suspect = traceback_signal or stage_failure
    incomplete=(observation.get('coverage')=='top_level_bash_only' and not observation.get('complete'))
    checked = 'unknown'
    # Deliberately narrow: an actual test summary, no failures/errors, complete
    # capture, and successful process. This validates only that public check.
    args=result.command.argv
    if args and PurePath(args[0]).name in ('sh','dash','zsh','ksh'):
        incomplete=True  # No PIPESTATUS-equivalent probe here; do not invent one.
    explicit_pytest=bool(args and (PurePath(args[0]).name in ('pytest','py.test') or
        len(args)>2 and PurePath(args[0]).name.startswith('python') and list(args[1:3])==['-m','pytest']))
    if (explicit_pytest and process_ok and not suspect and not incomplete and not result.output_truncated
            and re.search(r'(?m)^=+ .*\b[1-9]\d* passed\b.* =+$', combined)
            and not re.search(r'\b[1-9]\d* (failed|errors?)\b', combined)):
        checked = 'public_check_passed'
    return dict(process_succeeded=process_ok, execution_clean=process_ok and not suspect and not incomplete,
                failure_observed=not process_ok,
                suspected_failure=suspect, check_status=checked,
                signals=(["python_traceback"] if traceback_signal else []) +
                        (["nonzero_shell_stage"] if stage_failure else []) +
                        (["status_coverage_incomplete"] if incomplete else []),
                shell=observation, task_success=None)
