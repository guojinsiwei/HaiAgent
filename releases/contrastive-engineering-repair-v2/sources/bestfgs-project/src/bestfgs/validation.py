"""Public-check evidence, not an official success judge.

Exit zero remains the contract for assertion/test commands. Explicit failure
summaries veto that contract (some simulators/reporters always exit zero).
Unknown task semantics still require a real assertion supplied by the policy.
"""
import re


def validation_passed(result):
    if not result.succeeded or result.output_truncated:
        return False
    text = result.stdout + '\n' + result.stderr
    failures = (
        r'^\s*FAILED\s*\(',                       # unittest
        r'^.*\b[1-9]\d* failed\b.*$',             # pytest summary
        r'^\s*(?:FAIL|ERROR):\s*test',
        r'^\s*Deadline met:\s*0\s*/\s*[1-9]\d*', # zero-completion simulation
        r'^\s*(?:Normalized|Overall score):\s*0(?:\.0+)?\s*$',
    )
    return not any(re.search(p, text, re.MULTILINE) for p in failures)


def measurements(results):
    """Comparable public scalar scores from verification stdout only.

Only this explicitly named higher-is-better CLI score is understood. Arbitrary
    numbers, persisted JSON score files, costs, accuracy guesses, and model
    claims are not ranked as rewards. As with any model-written test, the
    verifier command itself must implement a sound task-specific assertion.
"""
    values = {}
    for result in results:
        found = re.findall(r'^\s*Normalized:\s*(0(?:\.\d+)?|1(?:\.0+)?)\s*$',
                           result.stdout, re.MULTILINE)
        if validation_passed(result) and len(found) == 1:
            values[result.command.normalized()] = float(found[0])
    return values
