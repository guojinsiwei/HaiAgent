"""Evidence-linked retirement of pending context; omission is never deletion."""
FIELDS = ('unresolved_issues', 'incomplete_plans', 'analysis_and_conclusions')

def merge_pending_context(previous, proposed, changes, outcome):
    if not isinstance(changes, list) or len(changes) > 12:
        raise ValueError('context_changes must be a list of at most 12 explicit updates')
    retired = {field: set() for field in FIELDS}
    evidence_notes = []
    channels = {'command': outcome.command_results, 'automatic_validation': outcome.validation_results,
                'functional_validation': outcome.functional_validation_results}
    for change in changes:
        required = {'field', 'item', 'status', 'source_channel', 'source_index', 'evidence_quote', 'reason'}
        if not isinstance(change, dict) or set(change) != required:
            raise ValueError('context_changes requires exact field/item/status/source/evidence/reason')
        field, item = change['field'], change['item']
        if not isinstance(field, str) or field not in FIELDS or not isinstance(item, str) or item not in getattr(previous, field):
            raise ValueError('Context change must name an exact existing item in an allowed field')
        if change['status'] not in ('resolved', 'invalidated'):
            raise ValueError('Context item must be explicitly resolved or invalidated')
        channel, index = change['source_channel'], change['source_index']
        if not isinstance(channel, str) or channel not in channels or type(index) is not int or not 0 <= index < len(channels[channel]):
            raise ValueError('Context change references no actual result')
        result = channels[channel][index]
        quote, reason = change['evidence_quote'], change['reason']
        if not isinstance(quote, str) or not 1 <= len(quote.strip()) <= 500 or not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 400:
            raise ValueError('Context change requires bounded non-empty evidence and reason')
        if result.timed_out or result.blocked or result.output_truncated:
            raise ValueError('Incomplete/blocked result cannot retire pending context')
        if quote not in result.stdout and quote not in result.stderr:
            raise ValueError('Context change quote is absent from the referenced result')
        retired[field].add(item)
        evidence_notes.append(f"Context {change['status']} [{field}]: {item}; "
            f"action={outcome.action.action_id}, source={channel}[{index}], "
            f"evidence={quote!r}, reason={reason}. Model interpretation, not official success.")
    merged = dict(proposed)
    for field in FIELDS:
        additions = proposed.get(field, [])
        if not isinstance(additions, (list, tuple)) or any(not isinstance(v, str) or not v.strip() for v in additions):
            raise ValueError(f'{field} must contain non-empty strings')
        merged[field] = list(dict.fromkeys(v for v in (*getattr(previous, field), *additions)
                                          if v not in retired[field]))
    merged['analysis_and_conclusions'] = list(dict.fromkeys((*merged['analysis_and_conclusions'], *evidence_notes)))
    return merged
