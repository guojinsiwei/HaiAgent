"""Bounded, non-semantic feedback for unusable JSON model responses."""

REPAIRABLE_OUTPUT = {'output_length', 'json_syntax', 'json_root_type', 'empty_content'}


def repair_feedback(detail, max_tokens=None):
    code = detail if detail in REPAIRABLE_OUTPUT else 'unusable_response'
    prefix = 'Protocol validation failed: ' + code + '. '
    if code == 'output_length':
        limit = str(max_tokens) if type(max_tokens) is int and max_tokens > 0 else 'configured'
        return (prefix + 'The response was truncated at the ' + limit + ' output-token limit. '
                'Return ONE much shorter complete JSON object in the requested schema. '
                'For code edits, emit only one small executable edit or file chunk now; '
                'perform remaining edits in later actions. Do not repeat the entire long script. '
                'Do not continue the truncated JSON. Keep optional explanations brief. '
                'Nothing from the rejected response was executed; previously completed edits remain.')
    return (prefix + 'Return exactly ONE complete valid JSON object matching the requested schema. '
            'No prose, Markdown fences, additional JSON objects or trailing text. '
            'Escape newlines, backslashes and quotes inside JSON strings. '
            'Keep the response compact; split long code edits across future actions. '
            'Nothing from the rejected response was executed.')
