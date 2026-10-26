"""No provider request may bypass a configured campaign ledger."""
import json
import os
import time
import urllib.error
import urllib.request
import uuid


class SpendingStopped(RuntimeError): pass


def total_usage(usage):
    if not isinstance(usage, dict): return None
    required = ('input_tokens', 'output_tokens')
    if any(type(usage.get(k)) is not int or usage[k] < 0 for k in required): return None
    extra = [usage.get(k, 0) for k in ('cache_read_input_tokens', 'cache_creation_input_tokens')]
    if any(type(v) is not int or v < 0 for v in extra): return None
    return sum(usage[k] for k in required)+sum(extra)


class SpendingClient:
    def __init__(self):
        self.url = os.environ.get('CAMPAIGN_BUDGET_URL')
        self.token = os.environ.get('CAMPAIGN_BUDGET_TOKEN', '')
        self.job = os.environ.get('CAMPAIGN_BUDGET_JOB', '')
        self.arm = os.environ.get('CAMPAIGN_BUDGET_ARM', '')
        if os.environ.get('CAMPAIGN_BUDGET_REQUIRED') == '1' and not (self.url and self.token and self.job and self.arm):
            raise SpendingStopped('budget_configuration_missing')

    def call(self, path, value):
        req = urllib.request.Request(self.url+path, json.dumps(value).encode(),
            headers={'Authorization':'Bearer '+self.token, 'Content-Type':'application/json'})
        try:
            # The private ledger must not traverse the provider CONNECT proxy.
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=10) as res:
                return json.loads(res.read(8192))
        except urllib.error.HTTPError as error:
            try: reason=json.loads(error.read(8192)).get('error','budget_service_unavailable')
            except ValueError: reason='budget_service_unavailable'
            raise SpendingStopped(reason) from None
        except (OSError, ValueError):
            raise SpendingStopped('budget_service_unavailable') from None

    def reserve(self, endpoint, payload, seconds):
        if not self.url: return None
        request=dict(id=uuid.uuid4().hex, job=self.job, arm=self.arm, endpoint=endpoint,
                     model=payload['model'], max_tokens=payload['max_tokens'])
        deadline=time.monotonic()+seconds
        while True:
            try: return self.call('/reserve',request)['id']
            except SpendingStopped as error:
                if str(error)=='campaign_budget_exhausted': self.call('/halt',dict(reason=str(error),job=self.job))
                if str(error) != 'waiting_for_inflight_usage' or time.monotonic()+1 >= deadline: raise
                time.sleep(1)

    def settle(self, lease, usage):
        if lease is None: return
        result=self.call('/settle',dict(id=lease,tokens=cost_usage(usage)))
        if result.get('halt_reason') or result.get('task_halt_reason'): raise SpendingStopped(result.get('halt_reason') or result['task_halt_reason'])


def cost_usage(usage):
    if total_usage(usage) is None:return None
    return (usage['input_tokens']*200+usage['output_tokens']*800+usage.get('cache_read_input_tokens',0)*4+usage.get('cache_creation_input_tokens',0)*200+99)//100
