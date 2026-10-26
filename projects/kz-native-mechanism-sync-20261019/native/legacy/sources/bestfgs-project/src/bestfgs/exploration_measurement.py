"""Preregistered scalar observations, with KZDSH exploration-v2 semantics."""
import math
import re
import json
from copy import deepcopy

OPPOSITE = {'eq': 'ne', 'ne': 'eq', 'lt': 'gte', 'gte': 'lt', 'lte': 'gt', 'gt': 'lte'}


def text(value):
    return isinstance(value, str) and bool(value.strip()) and '\0' not in value


def scalar_type(value):
    if type(value) is bool:
        return 'boolean'
    if type(value) in (int, float) and math.isfinite(value):
        return 'number'
    if isinstance(value, str):
        return 'string'
    return None


def validate_measurement(value):
    if not isinstance(value, dict) or not text(value.get('hypothesis')):
        raise ValueError('Exploration requires a hypothesis.')
    a, b = value.get('supports'), value.get('refutes')
    if not isinstance(a, dict) or not isinstance(b, dict):
        raise ValueError('Exploration requires supports and refutes.')
    result = deepcopy(value)
    if 'metric' in a or 'metric' in b:
        for p in (a, b):
            if (p.get('field') not in ('stdout', 'stderr') or not isinstance(p.get('metric'), str)
                    or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,79}', p['metric'])
                    or not isinstance(p.get('op'), str) or p['op'] not in OPPOSITE
                    or scalar_type(p.get('value')) is None
                    or p['op'] not in ('eq', 'ne') and scalar_type(p['value']) != 'number'):
                raise ValueError('Use a JSON scalar metric, field and a finite typed comparison.')
        if (a['field'] != b['field'] or a['metric'] != b['metric'] or OPPOSITE[a['op']] != b['op']
                or scalar_type(a['value']) != scalar_type(b['value']) or a['value'] != b['value']):
            raise ValueError('Predictions must complement the same metric and threshold.')
        if not text(value.get('alternative')) or not text(value.get('measurement')):
            raise ValueError('Explain the alternative hypothesis and measurement method.')
        result['mode'] = 'metric'
    else:
        for p in (a, b):
            if p.get('field') not in ('stdout', 'stderr') or not text(p.get('contains')) or len(p['contains']) > 240:
                raise ValueError('Literal observations require stdout|stderr and a nonempty marker up to 240 characters.')
        if a['field'] == b['field'] and (a['contains'] in b['contains'] or b['contains'] in a['contains']):
            raise ValueError('Predictions must distinguish their observations.')
        result['mode'] = 'literal'
    return result


def measure(experiment, row, usable):
    def unknown(reason, evidence=None):
        return dict(status='unknown', reason=reason, evidence=evidence or [])
    if not usable:
        return unknown('execution_unusable')
    if experiment.get('mode') != 'metric':
        evidence = [dict(field=experiment[k]['field'], quote=experiment[k]['contains'], matched_prediction=k)
                    for k in ('supports', 'refutes') if experiment[k]['contains'] in row.get(experiment[k]['field'], '')]
        return unknown('literal_observation_only' if evidence else 'no_predicted_observation', evidence)
    p = experiment['supports']
    values = []
    for line in row.get(p['field'], '').splitlines():
        try:
            obj = json.loads(line)
        except (ValueError, TypeError):
            continue
        if isinstance(obj, dict) and p['metric'] in obj:
            values.append(obj[p['metric']])
    if not values:
        return unknown('missing_measurement')
    if any(scalar_type(v) != scalar_type(p['value']) or v != values[0] for v in values):
        return unknown('ambiguous_or_mistyped_measurement')
    v, threshold = values[0], p['value']
    matched = {'eq': lambda: v == threshold, 'ne': lambda: v != threshold,
               'lt': lambda: v < threshold, 'lte': lambda: v <= threshold,
               'gt': lambda: v > threshold, 'gte': lambda: v >= threshold}[p['op']]()
    return dict(status='supported' if matched else 'refuted', reason='measured_prediction_match',
                evidence=[dict(field=p['field'], metric=p['metric'], value=v, op=p['op'], threshold=threshold)],
                measurement=experiment['measurement'], provenance='solver_authored_measurement_semantics_unverified')
