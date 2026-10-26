"""One explicit action per response. Never salvage the first of multiple actions."""
import hashlib
import json

TOOL_NAME = 'choose_action'


def schema_bytes(config):
    if config.response_protocol != 'tool_call':
        return 0
    # Reserve native tool definition and protocol envelope under the shared budget.
    return len(json.dumps(action_tool(config.method, config.subgoal_scaffold), ensure_ascii=False, sort_keys=True,
                          separators=(',', ':')).encode()) + 256


def action_tool(method, subgoal_scaffold=True):
    properties = {
        'action': {'type': 'string', 'enum': ['run', 'submit']},
        'argv': {'type': 'array', 'items': {'type': 'string'}, 'description': 'Required for run. One executable and its arguments.'},
        'cwd': {'type': 'string'}, 'stdin': {'type': ['string', 'null']},
        'timeout_seconds': {'type': 'number'}, 'purpose': {'type': 'string'},
        'summary': {'type': 'string', 'description': 'Required for submit. Do not include run fields when submitting.'},
    }
    if method == 'hai':
        properties['strategy'] = {'type': 'string', 'description': 'Stable short label for the underlying approach used by this run action. Reuse it for the same method; do not rename a stalled strategy.'}
        if subgoal_scaffold:
            properties['subgoal'] = {'type': 'string', 'description': 'Stable short label for the immediate objective this action advances. Keep it while trying different strategies; change it only when focus changes. Do not emit a full plan.'}
        properties['retry_reason'] = {'type': 'string', 'description': 'Required when decision_advice reports repeated identical output and you choose that same action again. Explain expected changed evidence, bounded polling, or a necessary revalidation. Otherwise omit.'}
        properties['memory'] = {'type': 'object', 'description': 'Optional supported task-local finding, not required.',
            'properties': {'conclusion': {'type': 'string'}, 'applies_when': {'type': 'string'},
                'evidence_ids': {'type': 'array', 'items': {'type': 'string'}},
                'kind': {'type': 'string', 'enum': ['finding', 'constraint', 'procedure', 'failure', 'recovery']},
                'dependencies': {'type': 'array', 'items': {'type': 'string', 'enum': ['workspace', 'environment']}}},
            'required': ['conclusion', 'applies_when', 'evidence_ids'], 'additionalProperties': False}
    return {'type': 'function', 'function': {'name': TOOL_NAME,
        'description': 'Choose exactly ONE next action: run one command OR submit. Never issue multiple calls; wait for feedback before deciding again.',
        'parameters': {'type': 'object', 'properties': properties, 'required': ['action'], 'additionalProperties': False}}}


def strict_object(text):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate JSON field: ' + key[:80])
            result[key] = value
        return result
    def invalid_constant(_):
        raise ValueError('Non-finite JSON number')
    value = json.loads(text, object_pairs_hook=unique, parse_constant=invalid_constant)
    if not isinstance(value, dict):
        raise ValueError('Exactly one action object required, not an array/scalar')
    return value


def response_diagnostic(response):
    """Bounded excerpts; caller applies Recorder redaction BEFORE this function."""
    text = response.get('content', '')
    if not isinstance(text, str):
        text = ''
    result = {'content_chars': len(text), 'content_sha256': hashlib.sha256(text.encode()).hexdigest(),
              'head': text[:1500], 'tail': text[-500:] if len(text) > 1500 else '',
              'excerpt_truncated': len(text) > 1500, 'transport_error': response.get('protocol_error'),
              'classification': 'invalid_action'}
    transport_classification = response.get('protocol_classification')
    tool_call_audit = response.get('tool_call_audit')
    if isinstance(tool_call_audit, dict):
        # Produced by the transport from types, lengths and hashes only.
        result['tool_call_audit'] = tool_call_audit
    if isinstance(transport_classification, str):
        result['classification'] = transport_classification
        return result
    # Inspect structure, without executing or silently repairing the result.
    try:
        _, offset = json.JSONDecoder().raw_decode(text.lstrip())
        trailing = text.lstrip()[offset:].strip()
        result['classification'] = 'extra_after_json' if trailing else 'schema_error'
        if trailing:
            result['trailing_head'] = trailing[:300]
            try:
                json.JSONDecoder().raw_decode(trailing)
                result['classification'] = 'multiple_json_values'
            except ValueError:
                result['classification'] = 'text_after_json'
    except (ValueError, RecursionError):
        result['classification'] = 'fenced_json' if text.lstrip().startswith('```') else 'malformed_json'
    return result
