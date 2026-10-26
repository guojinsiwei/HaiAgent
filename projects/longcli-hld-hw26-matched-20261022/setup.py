"""Prepare an isolated, no-hint HW26 attempt; never modify the live campaign."""
from pathlib import Path
import ast, hashlib, json, shutil, subprocess, sys, tempfile, time

ROOT = Path(__file__).resolve().parent
PARENT = ROOT.parent/'longcli-hld-full20-triple-20261022'
JOB = 'hld-hw26-repeat--ap1400_2_hw26'

def read(p): return json.loads(p.read_text())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p, value): p.write_text(json.dumps(value, indent=2, ensure_ascii=False))
def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)

assert not (ROOT/'preflight.json').exists(), 'Already staged'
base = read(PARENT/'protocol.json')
row = next(r for r in base['tasks'] if r['task']=='ap1400_2_hw26')
assert sha(Path(row['starter_path'])) == row['starter_sha256']
for name in ['common.py', 'spending.py', 'input-manifest.json']:
    shutil.copy2(PARENT/name, ROOT/name)
for name in ['runtime', 'upstream']:
    (ROOT/name).symlink_to(PARENT/name, target_is_directory=True)
(ROOT/'empty-tests').mkdir()

runner = (PARENT/'runner.py').read_text()
runner = once(runner, "job='hld--'+row['task']", "job='hld-hw26-repeat--'+row['task']")
runner = once(runner, "(ROOT/'empty-tests','/tests',True)]", "(ROOT/'empty-tests','/tests',True),(ROOT/'entry-run.mjs','/opt/entry-run.mjs',True)]")
runner = once(runner, "'/opt/node/bin/node','/opt/kz/container-run.mjs'", "'/opt/node/bin/node','/opt/entry-run.mjs'")
(ROOT/'runner.py').write_text(runner)
grader = (PARENT/'college_grader.py').read_text()
grader = once(grader, '# Install shared claims at the first grading boundary, before queued jobs launch.\nfrom capacity_extension import install_live\ninstall_live()\n', '')
(ROOT/'college_grader.py').write_text(grader)
def grade_ast(s): return ast.dump(next(n for n in ast.parse(s).body if isinstance(n,ast.FunctionDef) and n.name=='grade'))
assert grade_ast(grader) == grade_ast((PARENT/'college_grader.py').read_text())

entry = (PARENT/'container-run.before-limit-extension.mjs').read_text()
entry = once(entry, "from './deadline.mjs'", "from '/opt/kz/deadline.mjs'")
for old,new in [('route.patch.yml','route-high-output.patch.yml'),('.runtime/kz.patch.yml','.runtime/kz-high-limits.patch.yml'),('.runtime/hld-new-context.patch.yml','.runtime/hld-high-context.patch.yml')]:
    entry = once(entry, "'"+old+"'", "'"+new+"'")
entry = once(entry, "const cwd=process.cwd();", "fs.writeFileSync(logs+'/effective-limits.json',JSON.stringify({requests:800,max_output_tokens:32768,task_limit_cny:24,campaign_limit_cny:480,algorithm:'HLD v8',fresh_attempt:true,no_hints:true}));\nconst cwd=process.cwd();")
(ROOT/'entry-run.mjs').write_text(entry)
protocol = {**base, 'experiment':ROOT.name, 'tasks':[row], 'methods':['hld-hw26-repeat'],
    'total_trials':1, 'concurrency':1, 'requests_per_task':800, 'max_output_tokens':32768,
    'task_budget_cny':24, 'campaign_budget_cny':480, 'shared_ledger':str(PARENT/'spending.sqlite'),
    'resource_limit_overrides':[], 'replaces_voided_experiment':None,
    'fresh_attempt':True, 'diagnostic_hints_to_solver':False, 'old_solution_to_solver':False,
    'original_score_preserved':True, 'rerun_not_substituted_into_first_attempt_aggregate':True}
save(ROOT/'protocol.json',protocol)

sys.path.insert(0,str(ROOT))
from spending import Ledger, BudgetError
profile = read(PARENT/'budget-profile.json')
def scoped(path):
    ledger=Ledger(path,profile)
    ledger.profile={**profile,'jobs':[JOB],'requests_per_task':800,'max_output_tokens':32768}
    return ledger
with tempfile.TemporaryDirectory(prefix='offline-',dir=ROOT) as tmp:
    ledger=scoped(Path(tmp)/'ledger.sqlite')
    req=dict(id='1',job=JOB,arm='kz',endpoint=profile['endpoint'],model=profile['model'],max_tokens=32768)
    assert ledger.reserve(req)['reserved_microcny']==518144
    ledger.settle(dict(id='1',tokens=0))
    for field,value,reason in [('job','hld--ap1400_2_hw26','job_not_authorized'),('max_tokens',32769,'invalid_output_reservation')]:
        try: ledger.reserve({**req,field:value,'id':'bad'})
        except BudgetError as e: assert e.reason==reason
        else: raise AssertionError('Invalid reservation admitted')
    with ledger.db() as db:
        for i in range(798): db.execute('INSERT INTO calls VALUES (?,?,?,?,?,?,?)',(str(i+2),JOB,'kz',0,0,'settled',time.time()))
    ledger.reserve({**req,'id':'800'}); ledger.settle(dict(id='800',tokens=0))
    try: ledger.reserve({**req,'id':'801'})
    except BudgetError as e: assert e.reason=='per_task_request_limit'
    else: raise AssertionError('Request ceiling missing')
    with ledger.db() as db:
        db.execute('DELETE FROM calls');db.execute('INSERT INTO calls VALUES (?,?,?,?,?,?,?)',('spent',JOB,'kz',23900000,23900000,'settled',time.time()))
    try: ledger.reserve({**req,'id':'over24'})
    except BudgetError as e: assert e.reason=='per_task_budget_exhausted'
    else: raise AssertionError('Task money ceiling missing')
    with ledger.db() as db:
        db.execute('DELETE FROM calls');db.execute('INSERT INTO calls VALUES (?,?,?,?,?,?,?)',('spent','other-job','kz',479900000,479900000,'settled',time.time()))
    try: ledger.reserve({**req,'id':'over480'})
    except BudgetError as e: assert 'campaign' in e.reason,e.reason
    else: raise AssertionError('Campaign money ceiling missing')

for n in ['runner.py','common.py','spending.py','college_grader.py','worker.py']:
    compile((ROOT/n).read_text(),str(ROOT/n),'exec')
subprocess.run([str(ROOT/'runtime/node/bin/node'),'--check',str(ROOT/'entry-run.mjs')],check=True)
assert subprocess.check_output(['docker','image','inspect',row['image'],'--format','{{.Id}}'],text=True).strip()==row['image_id']
manifest=read(ROOT/'input-manifest.json')
for n,digest in manifest['files'].items():
    if '/tests/' in n or n.endswith('run-tests.sh') or '/parsers/' in n or n.endswith('harness.py'): assert sha(ROOT/n)==digest,n
assert min(shutil.disk_usage(ROOT).free,shutil.disk_usage('/var/lib/docker').free)>8*2**30
for n,needle in [('route-high-output.patch.yml','maxTokens: 32768'),('shared-budget-high.mjs','state.requests>=800'),('.runtime/kz-high-limits.patch.yml','maxRequests: 800'),('.runtime/hld-high-context.patch.yml','headroomTokens: 32768')]:
    assert needle in (ROOT/'runtime/kz'/n).read_text()
sealed=['runner.py','college_grader.py','common.py','spending.py','entry-run.mjs','worker.py','protocol.json','input-manifest.json']
sealed += ['runtime/kz/'+n for n in ['route-high-output.patch.yml','shared-budget-high.mjs','.runtime/kz-high-limits.patch.yml','.runtime/hld-high-context.patch.yml']]
save(ROOT/'preflight.json',dict(passed=True,model_calls=0,created=time.time(),hashes={n:sha(ROOT/n) for n in sealed},
    checks=['original starter hash','original instruction','fresh workspace','same official grader AST and hashes','same image','800 attempts','32768 output','24 CNY attempt ceiling','480 CNY shared ceiling','separate job allowlist','syntax checks','disk headroom']))
print(json.dumps(dict(staged=True,preflight=True,model_calls=0,job=JOB)))
