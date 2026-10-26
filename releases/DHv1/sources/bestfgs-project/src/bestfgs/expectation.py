"""Preregistered local observations, not a new gate or a task-success oracle."""
from .command_paths import command_words
from .lean_progress import normalize_workspace_path


EXPECTATION_INSTRUCTION = '''For each run action add ONE compact expected_observation.
Declare a concrete local observation BEFORE execution, not "task succeeds".
Choose one form:
{"kind":"build","artifact":"cow/kernel/kernel"} (clean build plus a new/changed artifact)
{"kind":"public_test","status":"passed"} (or "failed"; supported public-test parser only)
{"kind":"file_state","path":"output.txt","state":"file","changed":true}
  state is file, directory or missing; changed is optional.
{"kind":"output","stream":"stdout","contains":"specific positive marker",
 "not_contains":"optional conflicting marker"} (stdout, stderr or combined)
{"kind":"unknown","reason":"a short reason no reliable criterion is known yet"}
Paths are task-root-relative (cow/kernel/kernel), NOT relative to shell cd.
Error absence alone is not a positive criterion. Do not print/touch a marker merely
to satisfy an assertion. Output matches are observations, not validated test passes.
The next evidence.expectation reports matched, contradicted or unknown. Use it to
recheck the hypothesis or decide the next action; never treat unknown as failure.
A mismatch does not rule out an entire route. No automatic rollback/checkpoint.
'''


def _text(value, name, limit=240):
    if not isinstance(value, str) or not value.strip() or len(value) > limit or '\x00' in value:
        raise ValueError('invalid '+name)
    return value


def _path(value):
    raw = _text(value, 'workspace path', 512)
    if any(c in raw for c in '$`*?\n\r'):
        raise ValueError('path must be literal')
    return normalize_workspace_path(raw)


def prepare(value):
    """Malformed optional contracts become unknown, never protocol exceptions."""
    if value is None:
        return dict(kind='unknown', contract_status='missing', reason='expected_observation_missing')
    try:
        if not isinstance(value, dict):
            raise ValueError('expected_observation must be an object')
        kind = value.get('kind')
        if kind not in ('build', 'public_test', 'file_state', 'output', 'unknown'):
            raise ValueError('unsupported expectation kind')
        result = dict(kind=kind, contract_status='valid')
        if kind == 'build':
            result['artifact'] = _path(value.get('artifact'))
        elif kind == 'public_test':
            if value.get('status') not in ('passed', 'failed'):
                raise ValueError('public_test status must be passed or failed')
            result['status'] = value['status']
        elif kind == 'file_state':
            result['path'] = _path(value.get('path'))
            if value.get('state') not in ('file', 'directory', 'missing'):
                raise ValueError('file state must be file, directory or missing')
            result['state'] = value['state']
            if 'changed' in value:
                if type(value['changed']) is not bool:
                    raise ValueError('changed must be boolean')
                result['changed'] = value['changed']
        elif kind == 'output':
            stream = value.get('stream', 'combined')
            if stream not in ('stdout', 'stderr', 'combined'):
                raise ValueError('unsupported output stream')
            result.update(stream=stream, contains=_text(value.get('contains'), 'positive marker'))
            if 'not_contains' in value:
                marker = _text(value['not_contains'], 'conflicting marker')
                if result['contains'] in marker or marker in result['contains']:
                    raise ValueError('output markers must distinguish observations')
                result['not_contains'] = marker
        else:
            result['reason'] = _text(value.get('reason'), 'unknown reason')
        return result
    except ValueError as error:
        return dict(kind='unknown', contract_status='invalid', reason=str(error))


def paths(contract):
    if contract['kind'] == 'build':
        return [contract['artifact']]
    if contract['kind'] == 'file_state':
        return [contract['path']]
    return []


def observe(environment, contract, known=None):
    """Use existing public file inspection, never run an extra task command."""
    names = paths(contract)
    result = {p: (known or {}).get(p, 'unknown') for p in names}
    missing = [p for p in names if p not in (known or {})]
    if missing:
        try:
            extra = environment.dependency_state(missing)
            result.update({p: extra.get(p, 'unknown') for p in missing})
        except (OSError, ValueError, RuntimeError, TimeoutError, AttributeError, TypeError):
            pass  # Inspection failure cannot stop or change the task action.
    return result


def _state(value):
    if not isinstance(value, str):
        return 'unknown'
    if value == 'missing':
        return 'missing'
    if value.startswith('file:'):
        return 'file'
    if value.startswith('dir:'):
        return 'directory'
    return 'unknown'  # Symlinks/external/dynamic state are never inferred.


def evaluate(contract, action, result, assessment, before=None, after=None,
             stdout='', stderr='', terminal_incomplete=False):
    """Three-valued evaluation bound to this actual action/result only."""
    before, after = before or {}, after or {}
    review = dict(status='unknown', expected=contract, reason='unknown',
                  observed={}, local_progress=None, task_success=None,
                  route_invalidated=False, automatic_checkpoint=False,
                  instruction='Compare this local observation with the hypothesis; unknown is not failure.')

    def finish(status, reason, **fields):
        review.update(status=status, reason=reason, **fields)
        return review

    if contract['kind'] == 'unknown':
        return finish('unknown', contract['reason'])
    signals = assessment.get('signals', [])
    incomplete = (result.timed_out or result.blocked or result.output_truncated or terminal_incomplete
                  or 'status_coverage_incomplete' in signals)
    if incomplete:
        return finish('unknown', 'execution_or_capture_incomplete')
    kind = contract['kind']
    if kind == 'public_test':
        actual = assessment.get('check_status', 'unknown')
        if actual not in ('public_check_passed', 'public_check_failed'):
            return finish('unknown', 'no_supported_public_test_result')
        actual = actual.removeprefix('public_check_')
        return finish('matched' if actual == contract['status'] else 'contradicted',
                      'supported_public_test_result', observed=dict(status=actual),
                      local_progress=None)  # Passing alone does not prove improvement.
    if kind == 'output':
        output = {'stdout': stdout, 'stderr': stderr, 'combined': stdout+'\n'+stderr}[contract['stream']]
        positive = contract['contains'] in output
        negative = contract.get('not_contains') is not None and contract['not_contains'] in output
        if positive and negative:
            return finish('unknown', 'conflicting_output_markers',
                          observed=dict(positive_marker=True, conflicting_marker=True))
        return finish('matched' if positive and not negative else 'contradicted',
                      'literal_observation_only_not_a_test_pass',
                      observed=dict(positive_marker=positive, conflicting_marker=negative))
    path = paths(contract)[0]
    current = _state(after.get(path))
    old = _state(before.get(path))
    changed = before.get(path) != after.get(path) if old != 'unknown' and current != 'unknown' else None
    observed = dict(path=path, before=old, after=current, changed=changed)
    if kind == 'build':
        _, words = command_words(action)
        if not words or words[0].rsplit('/', 1)[-1] not in {
            'make', 'cmake', 'ninja', 'gcc', 'g++', 'cc', 'c++', 'clang', 'clang++', 'cargo'}:
            return finish('unknown', 'no_recognized_build_invocation', observed=observed)
        if result.return_code != 0 or assessment.get('suspected_failure'):
            return finish('contradicted', 'build_execution_failed', observed=observed, local_progress=False)
        if not assessment.get('execution_clean') or current == 'unknown':
            return finish('unknown', 'build_or_artifact_unverified', observed=observed)
        if current != 'file':
            return finish('contradicted', 'build_artifact_missing', observed=observed, local_progress=False)
        if changed is not True:
            return finish('unknown', 'artifact_preexisting_or_change_unverified', observed=observed)
        return finish('matched', 'clean_build_and_changed_artifact_not_full_correctness',
                      observed=observed, local_progress=True)
    if current == 'unknown' or ('changed' in contract and changed is None):
        return finish('unknown', 'file_state_unverified', observed=observed)
    matches = current == contract['state'] and ('changed' not in contract or changed == contract['changed'])
    return finish('matched' if matches else 'contradicted', 'public_file_state',
                  observed=observed)  # A file change alone is not task progress.
