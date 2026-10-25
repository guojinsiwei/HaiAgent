"""Apply the explicitly authorized per-task limits to the fresh runtime only."""
import json,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def configure(runtime):
    kz=runtime/'kz'
    for name in ('provider-guard.mjs','spending-client.mjs','messages-protocol.mjs','shared-budget.mjs'):
        shutil.copyfile(ROOT/name,kz/name)
    patch=kz/'.runtime/kz.patch.yml';text=patch.read_text()
    text=text.replace('budgetDisabled: true','budgetDisabled: false\n        maxRequests: 120\n        maxTools: 180\n        wallSeconds: 2700').replace('serverWallSeconds: 10800','serverWallSeconds: 2700')
    patch.write_text(text)
    for name in ('route.patch.yml','config/common.patch.yml'):
        p=kz/name;p.write_text(p.read_text().replace('32768','16384').replace('1000000','128000'))
    p=kz/'boot-guard.mjs';p.write_text(p.read_text().replace("budgetMode==='unlimited'","budgetMode==='bounded_peak_price_estimate'").replace('unbounded accounting unavailable','bounded accounting unavailable'))
    tasks=json.loads((ROOT/'tasks.json').read_text())['tasks']
    profile=dict(endpoint='https://api.taotoken.net/token/v1/messages',model='deepseek-flash',
        campaign_limit_microcny=40000000,task_limit_microcny=5000000,input_ceiling_tokens=128000,
        max_output_tokens=16384,requests_per_task=120,tools_per_task=180,solver_seconds=2700,
        rate_basis='TaoToken official deepseek-flash peak prices viewed 2026-10-16: input 2, cached input 0.04, output 8 CNY/M; estimate, not Credits invoice',
        rate_source='https://taotoken.net/models?modelId=deepseek-flash',
        jobs=[f'first-{i+1:02d}-kz-dsh-{t["name"]}' for i,t in enumerate(tasks)])
    (ROOT/'budget-profile.json').write_text(json.dumps(profile,indent=2))
