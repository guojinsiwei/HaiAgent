"""Recognize HLD's structured terminal budget event, never free-form model text."""
import json

MESSAGE='KZ per-task monetary ceiling; next request not sent, artifacts retained'

def hld_monetary_stop(live,arm,exit_valid,code):
    if arm!='hld' or not exit_valid or code!=1:return False
    terminal=None
    try:
        with (live/'dsh.jsonl').open() as stream:
            for line in stream:
                try:event=json.loads(line)
                except ValueError:continue
                if isinstance(event,dict) and event.get('type')=='status' and event.get('phase')=='turn_end':terminal=event
    except FileNotFoundError:return False
    reason=(terminal or {}).get('reason')
    return (isinstance(reason,dict) and reason.get('kind')=='error'
            and isinstance(reason.get('error'),dict)
            and reason['error'].get('message')==MESSAGE)
