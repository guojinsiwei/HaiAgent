import hashlib,json,subprocess,sys
from pathlib import Path
R=Path(__file__).resolve().parent
p=subprocess.run([sys.executable,'-m','unittest','test_boost'],cwd=R,capture_output=True,text=True)
(R/'acceptance.log').write_text(p.stdout+p.stderr);assert p.returncode==0,p.stderr
protocol=dict(total_concurrency=6,per_arm=2,preserve_old_children=True,only_transfer_pending=True,paid_tasks_not_repeated=True,shared_budget='Original 600 CNY ledger and cumulative 4 CNY per arm/task',runtime_changed=False,solver_seconds=2700)
(R/'protocol.json').write_text(json.dumps(protocol,indent=2))
files=[p for p in R.iterdir() if p.suffix in ('.py','.json','.gz') and p.name!='boost-seal.json']+[R/'dependencies/network_proxy.py']
(R/'boost-seal.json').write_text(json.dumps(dict(tests_passed=True,files={str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}),indent=2))
print('BOOST_SEALED; four takeover regression tests passed; existing runtime unchanged')
