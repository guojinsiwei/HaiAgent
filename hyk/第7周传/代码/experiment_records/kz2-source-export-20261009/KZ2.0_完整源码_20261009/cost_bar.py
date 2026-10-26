"""KZ per-task monetary safety barrier, separate from the frozen solver.

Peak CNY prices provide a conservative upper bound (not an invoice). All roles
and wire retries share one ledger. Unknown billing reserves the full worst-case
request. A future transport entry can reserve before every paid request; the
watchdog covers already-running, unmodified historical workers after responses.
"""
from decimal import Decimal
import json
import os
from pathlib import Path
import signal
import subprocess
import time

MILLION=Decimal(1000000)
LIMIT=Decimal('50')
HIT=Decimal('0.04');MISS=Decimal('2');OUTPUT=Decimal('8')
PRICE_SOURCE='https://api-docs.deepseek.com/zh-cn/quick_start/pricing/'
PRICE_AS_OF='2026-10-09'
MAX_INPUT=1000000;MAX_OUTPUT=32768


class CostBudgetStop(BaseException):
    """Safety boundary: ordinary model-error retry handlers must not swallow it."""
    pass


def number(value):
    return value if type(value) is int and value>=0 else None


def usage_cost(usage):
    if not isinstance(usage,dict):return None
    if any(k in usage and number(usage[k]) is None for k in
           ('prompt_tokens','completion_tokens','prompt_cache_hit_tokens','prompt_cache_miss_tokens')):
        return None
    total=number(usage.get('prompt_tokens'));out=number(usage.get('completion_tokens'))
    hit=number(usage.get('prompt_cache_hit_tokens'))
    miss=number(usage.get('prompt_cache_miss_tokens'))
    if total is None and hit is not None and miss is not None:total=hit+miss
    if total is None or out is None:return None
    if hit is None:
        details=usage.get('prompt_tokens_details')
        hit=number(details.get('cached_tokens')) if isinstance(details,dict) else None
    hit=hit or 0
    if hit>total or miss is not None and miss+hit!=total:return None
    miss=total-hit
    return (Decimal(hit)*HIT+Decimal(miss)*MISS+Decimal(out)*OUTPUT)/MILLION


def worst_request(max_output=MAX_OUTPUT):
    assert type(max_output) is int and 0<=max_output<=MAX_OUTPUT
    # Deliberately reserve the WHOLE model input capacity. No unsafe tokenizer
    # estimate, cache-hit assumption or shortened output request is involved.
    return (Decimal(MAX_INPUT)*MISS+Decimal(max_output)*OUTPUT)/MILLION


class Ledger:
    def __init__(self,limit=LIMIT):
        self.limit=Decimal(str(limit));self.spent=Decimal(0)
        self.pending=Decimal(0);self.attempts=0;self.uncertain=0
    def reserve(self,payload):
        assert payload['model']=='deepseek-flash'
        amount=worst_request(payload['max_tokens'])
        if self.spent+self.pending+amount>self.limit:
            raise CostBudgetStop('KZ per-task CNY cost ceiling')
        assert not self.pending,'one sequential shared transport per task'
        self.pending=amount;self.attempts+=1
    def settle(self,status,body):
        observed=None
        if status=='ok':
            try:
                parsed=json.loads(body)
                observed=usage_cost(parsed.get('usage')) if isinstance(parsed,dict) else None
            except (ValueError,TypeError):pass
        if observed is not None:
            if observed>self.pending:
                self.spent+=observed;self.pending=Decimal(0)
                raise CostBudgetStop('provider usage exceeded reserved model capacity')
            self.spent+=observed
        else:
            # Even HTTP/network failures are not silently credited as free.
            self.spent+=self.pending;self.uncertain+=1
        self.pending=Decimal(0)
    def snapshot(self):
        value=self.spent+self.pending
        return dict(name='KZ',limit_cny=str(self.limit),cost_upper_cny=str(value),
            confirmed_upper_cny=str(self.spent),reserved_cny=str(self.pending),
            progress=min(1,float(value/self.limit)),attempts=self.attempts,
            uncertain_billing_attempts=self.uncertain,price_source=PRICE_SOURCE,
            price_as_of=PRICE_AS_OF,price_basis='peak CNY upper bound; not actual invoice')


def install_transport_bar():
    """Call before original trial() in a NEW worker. Never change its prompts."""
    import budget_adapter
    from common import save
    original=budget_adapter.CheckedTransport.__init__
    ledgers={}
    def init(self,audit,transport=None):
        original(self,audit,transport)
        folder=audit.path.parent
        ledger=ledgers.setdefault(str(folder),Ledger())
        underlying=self.transport
        def guarded(endpoint,payload,key,seconds,recorder=None):
            try:ledger.reserve(payload)
            except CostBudgetStop:
                save(folder/'cost-stop.json',dict(ledger.snapshot(),reason='cost_budget_cny',
                    mode='atomic_pre_request_reservation',request_not_sent=True))
                raise
            save(folder/'cost-bar.json',ledger.snapshot())
            try:
                status,body=underlying(endpoint,payload,key,seconds,recorder=recorder)
            except BaseException:
                ledger.settle('uncertain',None);save(folder/'cost-bar.json',ledger.snapshot());raise
            try:ledger.settle(status,body)
            except CostBudgetStop:
                save(folder/'cost-stop.json',dict(ledger.snapshot(),reason='cost_budget_cny',
                    mode='provider_usage_exceeded_reserved_capacity',request_not_sent=False))
                raise
            save(folder/'cost-bar.json',ledger.snapshot())
            return status,body
        self.transport=guarded
    budget_adapter.CheckedTransport.__init__=init


def scan(path,offset=0,state=None):
    """Incremental billing-only JSONL scan; no prompt/key extraction/output."""
    state=state or {'charged':Decimal(0),'pending':Decimal(0),'attempts':0,
                    'usage_reports':0,'uncertain':0}
    with path.open('rb') as stream:
        stream.seek(offset)
        while True:
            start=stream.tell();raw=stream.readline()
            if not raw or not raw.endswith(b'\n'):stream.seek(start);break
            event=json.loads(raw);kind=event.get('event')
            if kind=='wire_request':
                if state['pending']:
                    state['charged']+=state['pending'];state['uncertain']+=1
                state['pending']=worst_request(event.get('payload',{}).get('max_tokens',MAX_OUTPUT))
                state['attempts']+=1
            elif kind=='wire_response':
                envelope=event.get('envelope')
                cost=usage_cost(envelope.get('usage')) if event.get('kind')=='ok' and isinstance(envelope,dict) else None
                if cost is not None:
                    state['charged']+=cost;state['usage_reports']+=1
                elif state['pending']:
                    state['charged']+=state['pending'];state['uncertain']+=1
                state['pending']=Decimal(0)
        return stream.tell(),state


def cut_off(root,job,state):
    from common import save,export_tree
    from docker_environment import docker,close_owned
    folder=root/'jobs'/job
    h=json.loads((folder/'health.json').read_text())
    if (folder/'summary.json').exists():return False
    c=json.loads((folder/'container.json').read_text())
    check=docker('inspect',c['name'],'--format','{{json .Config.Labels}}',check=False,seconds=10)
    if check.returncode:raise RuntimeError('cannot prove owned live container')
    labels=json.loads(check.stdout)
    assert labels.get('experiment')==root.name and labels.get('job')==job
    assert h['job']==job and h['task']==job.split('--',1)[1]
    # pid belongs to this freshly heartbeating owned task; no process environment,
    # credentials, command arguments or unrelated processes are inspected.
    pid=h['pid'];assert type(pid) is int and pid>1 and time.time()-h['updated']<600
    os.kill(pid,signal.SIGSTOP)
    if (folder/'summary.json').exists():os.kill(pid,signal.SIGCONT);return False
    os.kill(pid,signal.SIGKILL)
    close_owned(folder)
    artifact=export_tree(folder/'workspace',folder/'final-source.tar.gz',source_only=True)
    h.update(name='KZ',state='awaiting_grade',engineering_fault=None,
        stop_reason='cost_budget_cny',submitted=False,task_processes_stopped=True,
        actual_api_attempts=state['attempts'],artifact=artifact,updated=time.time(),ended=time.time(),
        cost_upper_cny=str(state['charged']),cost_cap_cny='50',
        cost_cap_mode='response-watchdog: an in-flight provider request can still be billed')
    save(folder/'summary.json',h);save(folder/'health.json',h)
    save(folder/'cost-stop.json',dict(reason='cost_budget_cny',limit_cny='50',
        observed_upper_cny=str(state['charged']),artifact_preserved=True,
        official_grade_still_required=True,algorithm_unchanged=True))
    return True


def watchdog(root):
    from common import save
    offsets={};states={};errors={};stopped=[]
    while True:
        file=root/'health.json';health=json.loads(file.read_text()) if file.exists() else {}
        bars=[]
        for folder in (root/'jobs').glob('1342--*'):
            log=folder/'model-audit.jsonl'
            if not log.exists():continue
            try:
                offset,state=scan(log,offsets.get(folder.name,0),states.get(folder.name))
                offsets[folder.name]=offset;states[folder.name]=state
                bar=dict(job=folder.name,name='KZ',limit_cny='50',
                    cost_upper_cny=str(state['charged']),inflight_reservation_cny=str(state['pending']),
                    progress=min(1,float(state['charged']/LIMIT)),
                    api_attempts=state['attempts'],usage_reports=state['usage_reports'],
                    uncertain_billing_attempts=state['uncertain'],price_basis='peak CNY upper bound')
                save(folder/'cost-bar.json',bar);bars.append(bar)
                if state['charged']>=LIMIT and folder.name in health.get('active',[]):
                    if cut_off(root,folder.name,state):stopped.append(folder.name)
            except Exception as error:
                errors[folder.name]=type(error).__name__
        done=health.get('state') in ('generation_complete','needs_attention') and not health.get('active')
        save(root/'cost-health.json',dict(name='KZ',updated=time.time(),state='complete' if done else
            'needs_attention' if errors else 'watching',jobs=bars,stopped=stopped,errors=errors,
            paid_api_calls=0,price_source=PRICE_SOURCE,price_as_of=PRICE_AS_OF,
            current_mode='external response watchdog; not atomic pre-request reservation',
            future_mode='install_transport_bar before worker start for atomic reservation'))
        if done:return
        time.sleep(1)


if __name__=='__main__':
    import sys
    assert sys.argv[1:] == ['--watch'], 'only owned run watchdog allowed'
    watchdog(Path(__file__).resolve().parent)
