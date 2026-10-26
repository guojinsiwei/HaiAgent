"""Fail-closed offline report readers. Parsing a report does not authenticate its producer."""


def source_success(source, task_id, source_format):
    if not isinstance(source, dict):
        raise ValueError('External report must be an object')
    if source_format == 'swe-instance-v1':
        row = source.get(task_id)
        if not isinstance(row, dict) or type(row.get('resolved')) is not bool:
            raise ValueError('SWE instance result missing for this task')
        if row.get('infra_failure') or row.get('ambiguous_failure'):
            raise ValueError('Infrastructure/ambiguous result is not a verified task outcome')
        return row['resolved']
    if source_format == 'swe-summary-v1':
        names = ('resolved_ids', 'unresolved_ids', 'error_ids', 'infra_failure_ids', 'ambiguous_failure_ids')
        for name in names:
            if name in source and (not isinstance(source[name], list) or any(not isinstance(i, str) for i in source[name])):
                raise ValueError('Malformed SWE result IDs')
        if any(task_id in source.get(name, []) for name in names[2:]):
            raise ValueError('Infrastructure/ambiguous result is not a verified task outcome')
        resolved, unresolved = task_id in source.get(names[0], []), task_id in source.get(names[1], [])
        if resolved == unresolved:
            raise ValueError('Task absent from, or conflicting in, SWE outcome lists')
        return resolved
    if source_format == 'fixture-reward-v1':
        # Explicit test/custom-verifier contract, NOT an official benchmark claim.
        reward = source.get('reward')
        if source.get('task_id') != task_id or type(reward) not in (int, float) or reward not in (0, 1):
            raise ValueError('Fixture requires matching task_id and binary numeric reward')
        return reward == 1
    raise ValueError('Unsupported source_format; require an explicit tested report adapter')
