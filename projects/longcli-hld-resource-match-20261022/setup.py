"""Prepare Scheme+COW with the same limits as the completed HW26 rerun."""
from pathlib import Path
import ast, hashlib, json, shutil, subprocess, sys, tempfile, time

ROOT = Path(__file__).resolve().parent
PARENT = ROOT.parent/'longcli-hld-full20-triple-20261022'
PREFIX = 'hld-resource-match'
TASKS = ['cs61_fa24_scheme', '61810_cow']
def read(p): return json.loads(p.read_text())
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p, obj): p.write_text(json.dumps(obj, indent=2, ensure_ascii=False))
def once(s, old, new):
    assert s.count(old) == 1, old
    return s.replace(old, new)

assert not (ROOT/'preflight.json').exists(), 'Already staged'
base = read(PARENT/'protocol.json')
rows = [next(r for r in base['tasks'] if r['task']==t) for t in TASKS]
for r in rows:
    assert sha(r['starter_path']) == r['starter_sha256']
    assert subprocess.check_output(['docker','image','inspect',r['image'],'--format','{{.Id}}'],text=True).strip() == r['image_id']
for name in ['common.py', 'spending.py', 'input-manifest.json']:
    shutil.copy2(PARENT/name, ROOT/name)
for name in ['runtime','upstream']:
    (ROOT/name).symlink_to(PARENT/name, target_is_directory=True)
(ROOT/'empty-tests').mkdir()
runner = once((PARENT/'runner.py').read_text(), "job='hld--'+row['task']", "job='"+PREFIX+"--'+row['task']")
runner = once(runner, "(ROOT/'empty-tests','/tests',True)]", "(ROOT/'empty-tests','/tests',True),(ROOT/'entry-run.mjs','/opt/entry-run.mjs',True)]")
runner = once(runner, "'/opt/node/bin/node','/opt/kz/container-run.mjs'", "'/opt/node/bin/node','/opt/entry-run.mjs'")
(ROOT/'runner.py').write_text(runner)
original_grader = (PARENT/'college_grader.py').read_text()
grader = once(original_grader, '# Install shared claims at the first grading boundary, before queued jobs launch.\nfrom capacity_extension import install_live\ninstall_live()\n', '')
(ROOT/'college_grader.py').write_text(grader)
def grade_ast(s): return ast.dump(next(n for n in ast.parse(s).body if isinstance(n,ast.FunctionDef) and n.name=='grade'))
assert grade_ast(grader) == grade_ast(original_grader)
entry = (PARENT/'container-run.before-limit-extension.mjs').read_text()
entry = once(entry, "from './deadline.mjs'", "from '/opt/kz/deadline.mjs'")
for old,new in [('route.patch.yml','route-high-output.patch.yml'),('.runtime/kz.patch.yml','.runtime/kz-high-limits.patch.yml'),('.runtime/hld-new-context.patch.yml','.runtime/hld-high-context.patch.yml')]:
    entry = once(entry, "'"+old+"'", "'"+new+"'")
entry = once(entry, 'const cwd=process.cwd();', "fs.writeFileSync(logs+'/effective-limits.json',JSON.stringify({requests:800,max_output_tokens:32768,context_tokens:128000,headroom_tokens:32768,task_limit_cny:24,campaign_limit_cny:480,algorithm:'HLD v8',fresh_attempt:true,no_hints:true}));\nconst cwd=process.cwd();")
(ROOT/'entry-run.mjs').write_text(entry)
save(ROOT/'protocol.json', {**base, 'experiment':ROOT.name, 'tasks':rows, 'methods':[PREFIX],
    'total_trials':2, 'concurrency':2, 'requests_per_task':800, 'max_output_tokens':32768,
    'context_tokens':128000, 'headroom_tokens':32768, 'task_budget_cny':24,
    'campaign_budget_cny':480, 'shared_ledger':str(PARENT/'spending.sqlite'),
    'resource_limit_overrides':[], 'replaces_voided_experiment':None,
    'selection_rule':'first-pass HLD functional score < Recuris AND first-pass HLD caps 400/16384',
    'selection':['cs61_fa24_scheme','ap1400_2_hw26','61810_cow'],
    'reused_completed_attempt':str(ROOT.parent/'longcli-hld-hw26-matched-20261022'),
    'excluded_already_high_caps':['61810_fs','61810_mmap'],
    'fresh_attempt':True,'diagnostic_hints_to_solver':False,'old_solution_to_solver':False,
    'original_score_preserved':True,'rerun_not_substituted_into_first_attempt_aggregate':True,
    'historical_recuris_context_tokens':1000000,'full_configuration_equivalence':False})
sys.path.insert(0,str(ROOT))
from worker import scoped
from spending import BudgetError
with tempfile.TemporaryDirectory(prefix='offline-',dir=ROOT) as tmp:
    ledger=scoped(Path(tmp)/'spending.sqlite')
    profile=ledger.profile
    req=dict(id='1',job=PREFIX+'--'+TASKS[0],arm='kz',endpoint=profile['endpoint'],model=profile['model'],max_tokens=32768)
    assert ledger.reserve(req)['reserved_microcny']==518144
    ledger.settle(dict(id='1',tokens=0))
    for field,value,reason in [('job','hld--'+TASKS[0],'job_not_authorized'),('max_tokens',32769,'invalid_output_reservation')]:
        try: ledger.reserve({**req,field:value,'id':'bad'})
        except BudgetError as e: assert e.reason==reason
        else: raise AssertionError('Invalid reservation admitted')
    with ledger.db() as db:
        for i in range(798): db.execute('INSERT INTO calls VALUES (?,?,?,?,?,?,?)',(str(i+2),req['job'],'kz',0,0,'settled',time.time()))
    ledger.reserve({**req,'id':'800'}); ledger.settle(dict(id='800',tokens=0))
    try: ledger.reserve({**req,'id':'801'})
    except BudgetError as e: assert e.reason=='per_task_request_limit'
    else: raise AssertionError('Request ceiling missing')
    for job,amount,reason in [(req['job'],23900000,'per_task_budget_exhausted'),('other-job',479900000,'campaign_budget_exhausted')]:
        with ledger.db() as db:
            db.execute('DELETE FROM calls'); db.execute('INSERT INTO calls VALUES (?,?,?,?,?,?,?)',('spent',job,'kz',amount,amount,'settled',time.time()))
        try: ledger.reserve({**req,'id':'over'})
        except BudgetError as e: assert e.reason==reason
        else: raise AssertionError('Money ceiling missing')
for n in ['runner.py','common.py','spending.py','college_grader.py','worker.py']:
    compile((ROOT/n).read_text(),str(ROOT/n),'exec')
subprocess.run([str(ROOT/'runtime/node/bin/node'),'--check',str(ROOT/'entry-run.mjs')],check=True)
for n,digest in read(ROOT/'input-manifest.json')['files'].items():
    if '/tests/' in n or n.endswith('run-tests.sh') or '/parsers/' in n or n.endswith('harness.py'):
        assert sha(ROOT/n)==digest,n
assert min(shutil.disk_usage(ROOT).free,shutil.disk_usage('/var/lib/docker').free)>8*2**30
sealed=['runner.py','college_grader.py','common.py','spending.py','entry-run.mjs','worker.py','protocol.json','input-manifest.json']
sealed += ['runtime/kz/'+n for n in ['route-high-output.patch.yml','shared-budget-high.mjs','.runtime/kz-high-limits.patch.yml','.runtime/hld-high-context.patch.yml']]
sealed += [str(p.relative_to(ROOT)) for p in (ROOT/'runtime/kz/src').rglob('*') if p.is_file()]
save(ROOT/'preflight.json',dict(passed=True,model_calls=0,created=time.time(),hashes={n:sha(ROOT/n) for n in sealed},
    checks=['original starters/instructions/images','official grader AST unchanged','official tests/parsers hashes','800 requests','32768 output','24/task and 480 shared ledger','new job allowlist','syntax','disk headroom','HLD source sealed']))
print(json.dumps(dict(staged=True,preflight=True,model_calls=0,tasks=TASKS)))
