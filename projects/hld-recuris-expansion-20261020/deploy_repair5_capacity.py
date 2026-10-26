"""Prepare verified repair and admission-only handoff; do not stop any solver."""
import ast
import copy
import hashlib
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
from storage import atomic_json
from recovery import process_identity, owned_alive

OUT = ROOT / "capacity10-20261020"
OUT.mkdir(exist_ok=True)

def backup(name):
    target = OUT / (name + ".before")
    if not target.exists():
        target.write_bytes((ROOT / name).read_bytes())

for name in ("ready.json", "effective_status.py"):
    backup(name)

source = (ROOT / "boost_campaign.py").read_text()
source = source.replace("PORT=29151", "PORT=29161")
source = source.replace("CONTROL=ROOT/'concurrency6-20261020'", "CONTROL=ROOT/'capacity10-20261020'")
source = source.replace("BudgetService(ROOT,port=29152)", "BudgetService(ROOT,port=29162)")
source = source.replace(
    "initial_rows([t['name'] for t in read(ROOT/'tasks.json')['tasks']],read(ROOT/'history.json'))",
    "read(CONTROL/'claimed-pending.json')['rows']")
source = source.replace("if len(active)>=6:break", "if len(active)>=10:break")
source = source.replace(
    "if sum(v['row']['arm']==row['arm'] for v in active.values()) >= 3:continue",
    "# Arm and global limits are applied by the capacity admission policy.")
start = source.index("\ndef boost_candidates(")
end = source.index("\n\nif __name__", start)
source = source[:start] + """
from tb_capacity_policy import choose, external_rows, space_ready
def boost_candidates(rows, active_arms):
    return choose(rows, active_arms, external_rows())
""" + source[end:]
source = source.replace("total_concurrency=6", "total_concurrency=10")
ast.parse(source)
(ROOT / "capacity_campaign.py").write_text(source)

source = (ROOT / "infra_repair3.py").read_text()
source = source.replace('infra-repair3-20261020', 'infra-repair5-20261020')
source = source.replace("assert len(failures) == 3", "assert len(failures) == 5")
source = source.replace("import campaign\n", "import campaign\nimport tb_capacity_policy\n")
source = source.replace(
    'campaign.space_ready(row["task"], {})',
    'tb_capacity_policy.space_ready(row["task"], {}, owner="infra-repair5-20261020")')
ast.parse(source)
(ROOT / "infra_repair5.py").write_text(source)

source = (ROOT / "effective_status.py").read_text()
needle = '    h["summary"] = summary(rows)'
insert = '''
    capacity=read(R / "capacity10-20261020/health.json")
    for x in capacity.get("rows", []):
        if x["job"] in by_job:by_job[x["job"]].update(copy.deepcopy(x))
    h["capacity"]={k:capacity.get(k) for k in ("state","summary","active","updated_utc")}
    h["active"]+=capacity.get("active", [])
    if capacity.get("state") not in (None,"finished","drained"):
        h["state"]="running_capacity10"
        h["updated_utc"]=capacity.get("updated_utc")
    repair5=read(R / "infra-repair5-20261020/health.json")
    for x in repair5.get("rows", []):
        original=by_job.get(x["original_job"])
        if original is None:continue
        original["repair_job"]=x["job"]
        if x["state"] in ("done","engineering_failure"):
            original.update(state=x["state"],result=x.get("result",{}),
                engineering_clean=x.get("result",{}).get("engineering_clean",False),
                repair_error=x.get("repair_error"))
        else:original.update(state="repair_"+x["state"],engineering_clean=False)
    h["repair5"]={k:repair5.get(k) for k in ("state","summary","active","updated")}
    if repair5.get("active"):h["active"].append(repair5["active"])
'''
assert source.count(needle) == 1
source = source.replace(needle, insert + needle)
ast.parse(source)
(ROOT / "effective_status.py").write_text(source)

# Exercise scheduling with ongoing old workers, repair workers and terminal rows.
import tb_capacity_policy as policy
rows = [dict(job=f"h{i}", arm="hld", state="pending") for i in range(20)]
rows += [dict(job=f"r{i}", arm="recuris", state="pending") for i in range(10)]
rows += [dict(job="finished", arm="hld", state="done")]
external = [dict(arm="hld") for _ in range(3)] + [dict(arm="recuris") for _ in range(5)]
chosen = policy.choose(rows, [], external)
assert len(chosen) == 2 and all(x["arm"] == "hld" for x in chosen)
chosen = policy.choose(rows, [], [])
assert len(chosen) == 10 and sum(x["arm"] == "hld" for x in chosen) == 7
assert len(policy.choose(rows[:20], [], [])) == 10
assert not policy.choose(rows, ["hld"] * 7 + ["recuris"] * 3, [])
assert policy.app_finished()

seal = json.loads((ROOT / "ready.json").read_text())
for name in ("capacity_campaign.py", "tb_capacity_policy.py", "infra_repair5.py", "effective_status.py"):
    seal["files"][name] = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
atomic_json(ROOT / "ready.json", seal)
import campaign
campaign.validate()
atomic_json(OUT / "offline-validation.json", dict(
    passed=True, model_calls=0, original_budget=True, global_limit=10,
    hld_target=7, hld_when_alone=10, no_active_task_interruption=True))

# The old controller acknowledges drain before any pending work can be claimed.
h = json.loads((ROOT / "concurrency6-20261020/health.json").read_text())
assert owned_alive(h["supervisor_identity"])
atomic_json(OUT / "before-handoff.json", h)
atomic_json(ROOT / "concurrency6-20261020/control.json", dict(
    command="drain", supervisor_identity=h["supervisor_identity"],
    reason="User requested AppWorld capacity transfer to HLD; active trials continue"))
print(json.dumps(dict(deployed=True, drain_requested=True, old_active=len(h["active"]))))
