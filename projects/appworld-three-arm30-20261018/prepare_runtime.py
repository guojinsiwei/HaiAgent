"""Freeze deployment overlays and test actual DSH runtime without model calls."""
from pathlib import Path
import json,hashlib,shutil,subprocess,tarfile
R=Path(__file__).resolve().parent
OLD=R.parent/'kz-dsh-exploration-v2-20261018'
TB=R.parent/'tb2-three-arm50-20261017'
assert not (R/'launch-once.marker').exists()
if not (R/'sources').exists():
    with tarfile.open(R/'sources.tar.gz') as archive:archive.extractall(R,filter='data')
lock=json.loads((R/'source-lock.json').read_text())
for name,expected in lock.items():assert hashlib.sha256((R/name).read_bytes()).hexdigest()==expected,name
def run(args,log):
    with (R/log).open('w') as f:subprocess.run(list(map(str,args)),stdout=f,stderr=subprocess.STDOUT,check=True,timeout=600)
node=TB/'runtime/node/bin/node';modules=TB/'runtime/kz/node_modules'
for arm in ['hld','kzdsh-new','dsh-baselines','recuris-dsh']:
    dest=R/'sources'/arm/'node_modules'
    if not dest.exists():dest.symlink_to(modules,target_is_directory=True)
run([node,'--test','--test-concurrency=2',*[R/'sources/hld/tests'/f for f in ['semantic-planner.test.mjs','semantic-integration.test.mjs']]],'hld-acceptance.log')
run([node,'--test','--test-concurrency=2',R/'sources/kzdsh-new/tests/exploration-v2.test.mjs'],'kzdsh-acceptance.log')
for arm in ['hld','kzdsh-new','recuris','dsh']:
    dest=R/'runtime'/arm;dest.mkdir(parents=True,exist_ok=True)
    for p in (OLD/'runtime/candidate').iterdir():
        if p.is_file():shutil.copy2(p,dest/p.name)
    for part in ['config','.runtime']:
        shutil.copytree(OLD/'runtime/candidate'/part,dest/part,dirs_exist_ok=True)
    src=R/'sources'/('hld' if arm=='hld' else 'kzdsh-new')
    shutil.copytree(src/'src',dest/'src',dirs_exist_ok=True)
    (dest/'node_modules').mkdir(exist_ok=True)
    text=(dest/'shared-budget.mjs').read_text().replace('>=120','>=400').replace('>=180','>=600').replace('requests:120,tools:180,seconds:2700,estimatePeakCny:4','requests:400,tools:600,seconds:7200,estimatePeakCny:8')
    (dest/'shared-budget.mjs').write_text(text)
    shutil.copy2(R/'boot-guard.mjs',dest/'boot-guard.mjs')
    if arm in ('hld','kzdsh-new'):
        text=(src/'config/kz.patch.yml').read_text().replace('__KZ_PLUGIN_PATH__','"/opt/kz/src/plugin.mjs"')
        text=text.replace('shellReceipts: false','shellReceipts: true').replace('maxRequests: 800','maxRequests: 400').replace('limitCny: 50','limitCny: 8').replace('maxInputTokens: 1000000','maxInputTokens: 128000').replace('maxOutputTokens: 32768','maxOutputTokens: 16384')
        (dest/'.runtime/kz.patch.yml').write_text(text)
    # Common action/tool surface for all arms. No delegated solvers or web search.
    common=(dest/'config/common.patch.yml').read_text()
    common+='\n- id: tool-bash\n  config:\n    enableRunInBackground: false\n    promoteOnTimeout: false\n- id: bash-sandbox\n  config:\n    timeoutMs: 120000\n    maxTimeoutMs: 120000\n'
    for name in ['tool-subagent-control','tool-subagent-list-agents','tool-web','tool-todo','tool-goal','skill-filesystem','session-telemetry-otel']:
        common+='- id: '+name+'\n  disabled: true\n'
    (dest/'config/common.patch.yml').write_text(common)
for name in ['recuris-dsh','dsh-baselines']:
    shutil.copytree(R/'sources'/name,R/'runtime'/name,dirs_exist_ok=True,ignore=shutil.ignore_patterns('node_modules','tests','scripts','__pycache__'))
    (R/'runtime'/name/'node_modules').mkdir(exist_ok=True)
profile=json.loads((OLD/'budget-profile.json').read_text())
tasks=json.loads((R/'task-manifest.json').read_text())['tasks']
profile.update(campaign_limit_microcny=720000000,task_limit_microcny=8000000,requests_per_task=400,tools_per_task=600,solver_seconds=7200,
               jobs=[a+'--'+t['task'] for t in tasks for a in ['hld','kzdsh-new','recuris','dsh']])
(R/'budget-profile.json').write_text(json.dumps(profile,indent=2))
protocol={'experiment':R.name,'benchmark':'AppWorld','split':'test_normal','seed':20261018,'methods':['hld','kzdsh-new','recuris','dsh'],
          'tasks':tasks,'trials':120,'workers':6,'model':'deepseek-flash','budget':profile,
          'image':json.loads((R/'image.json').read_text())['image'],'cross_task_memory':False,'official_feedback_to_solver':False,
          'automatic_paid_retry':False,'hld_reconnaissance_steps':8}
(R/'protocol.json').write_text(json.dumps(protocol,indent=2))
print('RUNTIME_PREPARED_WITHOUT_MODEL_CALLS',flush=True)
