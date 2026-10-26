"""Strict engineering receipts. Missing evidence is never successful evidence."""
import json
import math
from pathlib import Path


def read_receipt(path):
    try:
        value = json.loads(Path(path).read_text())
    except FileNotFoundError:
        return None, 'missing'
    except (ValueError, UnicodeError):
        return None, 'corrupt'
    if not isinstance(value, dict):
        return None, 'invalid_schema'
    return value, 'present'


def lifecycle_status(path, attempt_id=None):
    value, status = read_receipt(path)
    if value is None:
        return status, []
    if value.get('schema_version') != 2 or not isinstance(value.get('failures'), list):
        return 'invalid_schema', []
    if attempt_id is not None and value.get('attempt_id') != attempt_id:
        return 'identity_mismatch', value['failures']
    events = value.get('events')
    if not isinstance(events, list) or not all(isinstance(e, dict) for e in events):
        return 'invalid_schema', value['failures']
    if value['failures']:
        return 'failed', value['failures']
    stages = [e.get('stage') for e in events]
    required = ['collecting', 'artifacts_collected', 'verifying', 'verifier_finished',
                'cleanup_started', 'cleanup_succeeded']
    cursor = 0
    for stage in stages:
        if cursor < len(required) and stage == required[cursor]:
            cursor += 1
    if cursor != len(required) or value.get('stage') != 'cleanup_succeeded':
        return 'incomplete', []
    return 'succeeded', []


def valid_reward(reward):
    return type(reward) in (int, float) and math.isfinite(reward)
