"""KZ future-worker entry: monetary guard around the unmodified historic trial."""
import json
from common import ROOT,save,export_tree
from cost_bar import install_transport_bar,CostBudgetStop


def trial(row,key='',mock=False):
    if not mock:install_transport_bar()
    from runner import trial as original
    folder=ROOT/('acceptance-jobs' if mock else 'jobs')/(row['method']+'--'+row['task'])
    try:result=original(row,key,mock)
    except CostBudgetStop:
        # Original trial's finally closes the owned container and saves health.
        # Only this outer safety boundary catches a monetary stop, never the
        # solver's ordinary error/retry machinery.
        result=json.loads((folder/'summary.json').read_text())
    stop=folder/'cost-stop.json'
    if not mock and stop.exists():
        marker=json.loads(stop.read_text())
        if not result.get('artifact'):
            assert result.get('task_processes_stopped')
            result['artifact']=export_tree(folder/'workspace',folder/'final-source.tar.gz',source_only=True)
        result.update(name='KZ',state='awaiting_grade',stop_reason='cost_budget_cny',
            submitted=False,engineering_fault=None,cost_cap=marker,
            actual_api_attempts=marker['attempts'],
            cost_preflight_rejected_request=marker.get('request_not_sent',False))
        save(folder/'summary.json',result);save(folder/'health.json',result)
    return result
