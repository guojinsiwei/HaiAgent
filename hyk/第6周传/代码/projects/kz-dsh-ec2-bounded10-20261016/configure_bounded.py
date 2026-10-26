"""Build this authorized bounded experiment; never changes the reference project."""
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parent/'deploy/terminalbench'
def edit(name,old,new):
    path=ROOT/name;text=path.read_text()
    assert old in text,(name,old)
    path.write_text(text.replace(old,new))

p=ROOT/'experiment.json';config=json.loads(p.read_text())
config.update(schema_version=2,solver_seconds=2700,engineering_retry_batches=0)
p.write_text(json.dumps(config,indent=2))
edit('experiment.py','schema_version=1','schema_version=2')
edit('experiment.py','solver_seconds=10800, engineering_retry_batches=1','solver_seconds=2700, engineering_retry_batches=0')
edit('experiment.py',"max_trials_with_retry=config['task_count']*2","max_trials_with_retry=config['task_count']")
edit('experiment.py','paid_attempts_per_arm_task=2, no_automatic_paid_retries=False','paid_attempts_per_arm_task=1, no_automatic_paid_retries=True')
for name in ('experiment.py','prepare.py'):
    edit(name,'finish first pass; one final engineering-fault-only retry batch; no score-zero or valid wall-budget retries','one pass only; no automatic paid retries')
edit('experiment.py','One unpaid preflight per trial; one final engineering-fault retry batch.','One unpaid preflight per trial; no paid retry batch.')
edit('prepare.py',"    from build_runtime import build\n    build()","    from bounded_runtime import configure\n    configure(runtime)\n    from build_runtime import build\n    build()")
edit('prepare.py',"'serverWallSeconds: 10800'","'serverWallSeconds: 10800'")
edit('prepare.py',"    with tarfile.open(BASE/'runtime-final.tar.gz') as archive:\n        for name,digest in protocol['common_hashes'].items():\n            if hashlib.sha256(archive.extractfile('kz/'+name).read()).hexdigest()!=digest:\n                raise RuntimeError('Common runtime drift: '+name)","    protocol['bounded_design']=json.loads((ROOT/'budget-profile.json').read_text())")
edit('prepare.py',"protocol['budget']['server_solver_seconds']=config['solver_seconds']","protocol['budget']={'server_solver_seconds':config['solver_seconds'],'requests_per_task':120,'tools_per_task':180,'estimate_peak_cny_per_task':3,'estimate_peak_cny_campaign':30,'context_tokens':128000,'output_tokens':16384}")
edit('build_runtime.py',"    temporary=ROOT/'runtime-next.tar.gz'","    files += ['kz/'+n for n in ('provider-guard.mjs','spending-client.mjs','messages-protocol.mjs')]\n    temporary=ROOT/'runtime-next.tar.gz'")

# Reuse the tested persistent reservation mechanics; monetary units are now micro-CNY.
edit('spending.py',"profile['campaign_limit_fen'] * profile['package_tokens'] // profile['package_price_fen']","profile['campaign_limit_microcny']")
edit('spending.py',"campaign_limit_yuan=self.profile['campaign_limit_fen']/100","estimate_peak_cny=self.limit/1e6")
edit('spending.py',"reserve = p['input_ceiling_tokens'] + maximum","reserve = p['input_ceiling_tokens'] * 2 + maximum * 8")
edit('spending.py',"        with self.db() as db:\n            status = self._status(db)","        if request.get('job') not in p['jobs']:raise BudgetError('job_not_authorized',400)\n        with self.db() as db:\n            status = self._status(db)")
edit('spending.py',"            if status['settled_tokens'] + status['uncertain_tokens'] + reserve > self.limit:","            count,charged = db.execute(\"SELECT count(*),COALESCE(sum(CASE WHEN state='settled' THEN actual ELSE reserved END),0) FROM calls WHERE job=?\",(request['job'],)).fetchone()\n            if count >= p['requests_per_task']:raise BudgetError('per_task_request_limit')\n            if charged + reserve > p['task_limit_microcny']:raise BudgetError('per_task_budget_exhausted')\n            if status['settled_tokens'] + status['uncertain_tokens'] + reserve > self.limit:")
# Public API status names accurately identify the unit.
p=ROOT/'spending.py';text=p.read_text()
for stem in ('limit','settled','reserved','uncertain','remaining'):
    text=text.replace(stem+'_tokens',stem+'_microcny')
p.write_text(text)
edit('spending-client.mjs','    const tokens=totalUsage(usage);','    const tokens=costUsage(usage);')
edit('spending-client.mjs','export class SpendingClient {',"export function costUsage(usage) {\n  if(totalUsage(usage)===null)return null;\n  return Math.ceil((usage.input_tokens*200+usage.output_tokens*800+(usage.cache_read_input_tokens??0)*4+(usage.cache_creation_input_tokens??0)*200)/100);\n}\n\nexport class SpendingClient {")

# Keep the original lifecycle, add bounded accounting and stop signals.
edit('campaign.py','from experiment import validate_protocol','from experiment import validate_protocol\nfrom spending import BudgetService')
edit('campaign.py','PORT=28485','PORT=28515')
edit('campaign.py',"    validate()\n    with supervisor_lock(ROOT):","    validate()\n    with supervisor_lock(ROOT):")
edit('campaign.py',"        network_proxy=proxy_module()","        budget=BudgetService(ROOT,port=28516)\n        network_proxy=proxy_module()")
edit('campaign.py',"phase='retry' if retry_built else 'first',summary=summary(rows),rows=rows,","phase='retry' if retry_built else 'first',summary=summary(rows),rows=rows,spending=budget.snapshot(),")
edit('campaign.py',"                control=read(ROOT/'control.json')","                spending=budget.snapshot()\n                if spending.get('halt_reason'):\n                    for item in active.values():\n                        if not item['offline']:\n                            for live in (ROOT/'jobs'/item['row']['job']).glob('*/agent/live'):\n                                atomic_json(live/'budget-stop.json',{'reason':spending['halt_reason']})\n                    if not active:checkpoint('held_budget_or_provider');break\n                control=read(ROOT/'control.json')")
edit('campaign.py',"                    append_retry_batch(rows);retry_built=True","                    retry_built=True  # This explicitly authorized design has no paid retries.")
edit('campaign.py',"                    if auth_pause or draining or recovery_pause:break","                    if auth_pause or draining or recovery_pause or spending.get('halt_reason'):break")
edit('campaign.py',"                        if offline:env.pop('TAOTOKEN_API_KEY',None)","                        if offline:env.pop('TAOTOKEN_API_KEY',None)\n                        else:env.update(CAMPAIGN_BUDGET_REQUIRED='1',CAMPAIGN_BUDGET_URL=budget.url,CAMPAIGN_BUDGET_TOKEN=budget.token,CAMPAIGN_BUDGET_JOB=row['job'],CAMPAIGN_BUDGET_ARM='kz')")
edit('campaign.py','            proxy.shutdown()','            proxy.shutdown();budget.close()')
edit('campaign.py',"retry_batches=1,per_arm_concurrency=1","retry_batches=0,per_arm_concurrency=1")
edit('campaign.py',"wall.get('reason')=='solver_wall_limit_3h' and wall.get('limit_seconds')==10800","wall.get('reason')=='solver_wall_limit' and wall.get('limit_seconds')==2700")
edit('campaign.py',"    if out['budget_exhausted'] and clean:","    local_stop=read(live/'limit-stop.json') or read(live/'budget-stop.json')\n    out['provider']=read(live/'provider-state.json')\n    out['budget_stop']=local_stop\n    if local_stop.get('reason') in ('per_task_request_limit','per_task_tool_limit','per_task_budget_exhausted'):out['budget_exhausted']=True\n    if out['budget_exhausted'] and clean:")
edit('campaign.py',"    if out['auth_failure'] or malformed:out['engineering_clean']=False","    if out['auth_failure'] or malformed or out['provider'].get('kind') in ('refusal','protocol','transport','credentials','quota','invalid_request','accounting'):out['engineering_clean']=False")
edit('host_agent.py',"payload=dict(key=key,arm=self.arm", "payload=dict(spending={k:v for k,v in os.environ.items() if k.startswith('CAMPAIGN_BUDGET_')},key=key,arm=self.arm")
edit('host_agent.py',"'budget_mode':'unlimited'","'budget_mode':'bounded_peak_price_estimate'")
edit('container-run.mjs',"if(!['kz','dsh'].includes(bundle.arm))", "if(bundle.spending?.CAMPAIGN_BUDGET_REQUIRED!=='1')throw Error('Missing campaign ledger');\nif(!['kz','dsh'].includes(bundle.arm))")
edit('container-run.mjs','NO_PROXY:bundle.no_proxy,',"NO_PROXY:bundle.no_proxy+',10.123.0.1',...bundle.spending,")
edit('container-run.mjs',"'--use-env-proxy','--import','/opt/kz/route-audit.mjs'","'--use-env-proxy','--import','/opt/kz/provider-guard.mjs','--import','/opt/kz/route-audit.mjs'")
edit('container-run.mjs','deadline(child,10800','deadline(child,2700')
edit('container-run.mjs','// Same three-hour solver budget as native KZ; no protocol-error early stop.',"const watch=setInterval(()=>{for(const name of ['limit-stop.json','budget-stop.json','provider-stop.json'])if(fs.existsSync(logs+'/'+name))guard.terminate(name);},250);")
edit('container-run.mjs','guard.finish();','guard.finish();clearInterval(watch);')
edit('container-run.mjs',"timed_out:guard.expired,arm:bundle.arm,budget_mode:'unlimited'","timed_out:guard.reason==='solver_wall_limit',stopped_by:guard.reason,arm:bundle.arm,budget_mode:'bounded_peak_price_estimate'")
# Use repaired process-tree deadlines with a generic reason and preserved attempt IDs.
fixed=Path(__file__).resolve().parents[1]/'experiment_records/tb4-ctyun-firstpass-20261015/deadline.mjs'
# parents[1] is projects; the workspace is parents[2].
fixed=Path(__file__).resolve().parents[2]/'experiment_records/tb4-ctyun-firstpass-20261015/deadline.mjs'
(ROOT/'deadline.mjs').write_text(fixed.read_text().replace('solver_wall_limit_3h','solver_wall_limit'))
edit('seal.py',"'engineering-lifecycle-result.json')","'engineering-lifecycle-result.json','budget-profile.json')")
edit('validate_offline.py',"str(ROOT/'test_deadline.mjs')","str(ROOT/'test_deadline.mjs'),str(ROOT/'test-provider-guard.mjs'),str(ROOT/'test_bounded_transport.mjs')")

for name in ('test_campaign.py','test_engineering.py'):
    p=ROOT/name;p.write_text(p.read_text().replace('solver_wall_limit_3h','solver_wall_limit').replace('limit_seconds=10800','limit_seconds=2700').replace('"limit_seconds":10800','"limit_seconds":2700'))
edit('test_engineering.py',"self.assertFalse(fields['no_automatic_paid_retries'])","self.assertTrue(fields['no_automatic_paid_retries'])")
edit('test_engineering.py',"fields['paid_attempts_per_arm_task'],2","fields['paid_attempts_per_arm_task'],1")
edit('test_engineering.py',"fields['max_trials_with_retry'],20","fields['max_trials_with_retry'],10")
edit('test_engineering.py','dict(experiment.protocol_fields(config),no_automatic_paid_retries=True)','dict(experiment.protocol_fields(config),no_automatic_paid_retries=False)')
print('Bounded deployment source prepared; no model calls.')
