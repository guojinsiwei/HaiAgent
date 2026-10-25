"""No model monitor: admit no more tasks after confirmed shared wire faults."""
import json
from pathlib import Path

OUTPUT_CODES={'json_syntax','json_root_type','empty_content','output_length','nonstop_finish'}
def terminal_action_errors(root):
    failures=[]
    for path in (Path(root)/'runs').glob('*/summary.json'):
        result=json.loads(path.read_text(encoding='utf-8'))
        if result.get('stop_reason') not in ('protocol_error','model_or_protocol_error_limit','api_error'):
            continue
        audit=path.parent/'model-audit.jsonl'
        if not audit.is_file():continue
        # Full prompts can make each audit hundreds of MB: bounded tail only.
        with audit.open('rb') as stream:
            stream.seek(max(0,audit.stat().st_size-4*1024*1024))
            lines=stream.read().decode('utf-8','replace').splitlines()
        last=None
        for line in reversed(lines):
            try:e=json.loads(line)
            except ValueError:continue
            if e.get('event') in ('model_error','model_response') and e.get('role')=='action':
                last=e;break
        if last and last['event']=='model_error':
            failures.append(dict(job=result['job'],error_code=last.get('error_code')))
    return failures

def shared_wire_failures(root):
    # A v8 policy refusal AFTER valid JSON is not a shared wire error.
    return [r['job'] for r in terminal_action_errors(root) if r['error_code'] in OUTPUT_CODES]

def terminal_provider_failures(root):
    return [r for r in terminal_action_errors(root) if r['error_code'] in
            {'http_400','http_401','http_402','http_403','http_404','http_422'}]
