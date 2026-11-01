"""Exercise all unchanged official graders on starter artifacts, no model feedback."""
from concurrent.futures import ThreadPoolExecutor
import json
import re
from common import ROOT,save,export_tree
from college_grader import grade

BAD_ENV=re.compile(r'(qemu-system-riscv64|riscv64-linux-gnu-gcc|riscv64-unknown-elf-gcc): (command not found|not found)|'
    r'No rule to make target [\x27\x22]?mkfs/mkfs\.c|/dev/null: Permission denied',re.I)

def check(row):
    name='roundtrip--'+row['task']
    report=ROOT/'fixture-grades'/name/'result.json'
    if report.exists():result=json.loads(report.read_text())
    else:
        archive=ROOT/('starter-'+row['task']+'.tar.gz')
        artifact=export_tree(ROOT/'public'/row['task'],archive)
        result=grade(name,archive,artifact['sha256'],fixture=True)
    output=ROOT/'fixture-grades'/name
    console=(output/'console.log').read_text(errors='replace')
    f2p=output/'test_output/f2p_output.txt'
    text=console+'\n'+(f2p.read_text(errors='replace') if f2p.exists() else '')
    faults=list(dict.fromkeys(m.group(0) for m in BAD_ENV.finditer(text)))
    item=dict(task=row['task'],grading_state=result['grading_state'],f2p=result.get('f2p'),
        p2p_is_pass=result.get('p2p_is_pass'),p2p_step_score=result.get('p2p_step_score'),
        p2p_count=result.get('p2p_count'),environment_faults=faults,
        error=result.get('error'),script_exit=result.get('script_exit'))
    print(json.dumps(item),flush=True)
    return item

def main():
    p=json.loads((ROOT/'protocol.json').read_text())
    rows=sorted(p['tasks'],key=lambda r:(not r['task'].startswith('61810_'),r['index']))
    # Same task containers/resources as final grading. Two offline lanes only.
    with ThreadPoolExecutor(max_workers=2) as pool:items=list(pool.map(check,rows))
    report=dict(passed=all(r['grading_state']=='complete' and not r['environment_faults'] for r in items),
        tasks=items,model_calls=0,unchanged_official_scripts=True,baseline_is_not_algorithm_performance=True)
    save(ROOT/'grading-acceptance.json',report)
    print(json.dumps(dict(passed=report['passed'],tasks=len(items),model_calls=0)),flush=True)
    raise SystemExit(0 if report['passed'] else 1)

if __name__=='__main__':main()
