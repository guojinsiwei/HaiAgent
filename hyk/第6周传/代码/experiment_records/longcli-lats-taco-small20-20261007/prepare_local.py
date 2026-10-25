"""Public immutable inputs and verbatim upstream modules, no model requests."""
import ast
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent
WORK = ROOT.parents[1]
BASE = ROOT.parent / 'longcli-dh-large20-20261007'
SMALL = ROOT.parent / 'longcli-reflexion20-college-20261006'

def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    for name in ('common.py', 'safe_process.py', 'grade_one.py', 'grading_adapter.py'):
        target = ROOT / name
        if not target.exists():
            shutil.copyfile(BASE / name, target)
    upstream = WORK / 'components' / 'TACO'
    vendor = ROOT / 'taco_native'
    vendor.mkdir(exist_ok=True)
    source = upstream / 'src/harbor/agents/terminus_2'
    if not (vendor / 'compression').exists():
        shutil.copytree(source / 'compression', vendor / 'compression',
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        shutil.copyfile(source / 'output_filter.py', vendor / 'output_filter.py')
        shutil.copyfile(upstream / 'LICENSE', vendor / 'LICENSE')
    shutil.copyfile(source / 'filter_prompts.py', vendor / 'filter_prompts.py')
    # Importing only this package avoids changing or importing the Harbor host.
    driver = next(n for n in ast.parse((BASE/'docker_environment.py').read_text()).body
                  if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name)
                  and t.id == 'COMMAND_DRIVER' for t in n.targets))
    value = ast.literal_eval(driver.value)
    if not (ROOT/'command_driver.py').exists():
        (ROOT/'command_driver.py').write_text(value, encoding='utf-8')
    p = json.loads((SMALL/'protocol.json').read_text())
    protocol = {k:p[k] for k in ('commit','tasks','model','grading_resources')}
    protocol.update(experiment=ROOT.name, methods=['lats','taco'],total_trials=40,
        temperature=0, thinking='disabled',max_turns=800,wire_attempt_ceiling=1600,
        retries_per_decision=1,max_tools=600,max_tokens=4096,input_bytes=48000,
        output_bytes=24000,command_seconds=300,cpu_per_task=2,memory_gib_per_task=8,
        process_address_space_gib=3,pids_limit=128,concurrency=2,
        taco_concurrency=1,canaries=['cs61_fa24_hog','61810_util'],
        lats={'samples':5,'exploration_weight':1.0,'value_weight':0.8,
              'rollouts':8,'depth':40,'reward':'public-only generated verification plus LM value; never official tests'},
        taco={'author_modules_verbatim':True,'host':'common linear CLI actor, not Terminus-2',
              'global_pool':'fresh campaign, fixed task order, seeds then online evolution',
              'compression_model':'deepseek-flash','auxiliary_calls_charged':True},
        budget_definition='800 logical calls all roles/repairs, <=1600 transport attempts, <=600 executed commands all branches',
        automatic_task_retry=False,sge_cancelled=True,storage_admission_floor=None,
        storage_policy='User waived free-space and total checkpoint thresholds; actual IO errors still stop admission')
    # Stable included canaries followed by fixed official task order.
    tasks = sorted(protocol['tasks'], key=lambda r:r['index'])
    protocol['tasks'] = [next(r for r in tasks if r['task']==n) for n in protocol['canaries']]
    protocol['tasks'] += [r for r in tasks if r['task'] not in protocol['canaries']]
    (ROOT/'protocol.json').write_text(json.dumps(protocol,indent=2),encoding='utf-8')
    provenance = {'papers':{'lats':'https://arxiv.org/abs/2310.04406',
                           'taco':'https://arxiv.org/abs/2604.19572'},'repositories':{},'vendor_hashes':{}}
    for label,repo in [('lats','LanguageAgentTreeSearch'),('taco','TACO')]:
        folder = WORK/'components'/repo
        provenance['repositories'][label] = subprocess.check_output(
            ['git','-C',str(folder),'rev-parse','HEAD'],text=True).strip()
    for f in vendor.rglob('*'):
        if f.is_file():provenance['vendor_hashes'][f.relative_to(ROOT).as_posix()] = digest(f)
    provenance['command_driver_sha256'] = digest(ROOT/'command_driver.py')
    provenance['driver_origin'] = str(BASE/'docker_environment.py')
    (ROOT/'source-provenance.json').write_text(json.dumps(provenance,indent=2),encoding='utf-8')
    print(json.dumps({'state':'prepared','methods':protocol['methods'],'paid_model_calls':0}))

if __name__ == '__main__':main()
