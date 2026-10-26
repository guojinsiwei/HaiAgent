"""Recover durable evidence after a controller stop without hiding the root fault."""
import json


def reconcile(directory, task, job, stopped, cleanup_error=None, halted=False):
    summary=directory/'summary.json'
    health=directory/'health.json'
    record=json.loads((summary if summary.exists() else health).read_text()) if summary.exists() or health.exists() else {}
    record.update(task=task,job=job,task_processes_stopped=stopped)
    if not summary.exists():
        result_path=directory/'result.json'
        if result_path.exists():
            result=json.loads(result_path.read_text())
            for field in ('stop_reason','error','model_calls','input_tokens','output_tokens'):
                if field in result:record[field]=result[field]
            if 'tool_calls' in result:record['root_tool_dispatches']=result['tool_calls']
            record['receipt_recovered_from']='result.json + health.json'
        else:record['receipt_recovered_from']='health.json' if health.exists() else 'controller'
        record['state']='engineering_failure' if record.get('error') or record.get('engineering_fault') else 'batch_interrupted'
        if not health.exists() and not result_path.exists():record['error_type']='MissingProcessReceipt'
        if halted and not record.get('error') and not record.get('engineering_fault'):
            record['interruption_reason']='peer_engineering_failure'
    if cleanup_error:
        record['cleanup_error']=type(cleanup_error).__name__
        receipt=getattr(cleanup_error,'cleanup_receipt',None)
        if receipt:
            record['cleanup_receipt']=receipt
            record['task_processes_stopped']=bool(receipt.get('stopped'))
    return record
