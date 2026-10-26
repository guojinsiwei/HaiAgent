"""A single complete object, optionally followed by exactly one extra brace.

No extraction from prose, unescaping, command rewriting, partial JSON completion,
or multiple-object selection. The decoded object is identical to the complete
prefix in the provider response. Normalization is audited by the caller.
"""
import json

def unique(pairs):
    value={}
    for key,item in pairs:
        if key in value:raise ValueError('duplicate_json_key')
        value[key]=item
    return value

def invalid_constant(value):raise ValueError('nonfinite_json_number')

def parse_complete_object(raw):
    if not isinstance(raw,str):raise ValueError('response_not_text')
    raw=raw.lstrip()
    value,end=json.JSONDecoder(object_pairs_hook=unique,parse_constant=invalid_constant).raw_decode(raw)
    if not isinstance(value,dict):raise ValueError('response_not_object')
    suffix=raw[end:].strip()
    if suffix not in ('','}'):raise ValueError('unexpected_content_after_object')
    return value,bool(suffix)
