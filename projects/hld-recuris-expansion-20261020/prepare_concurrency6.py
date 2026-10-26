"""Prepare scheduling-only changes, with shared original budget and task IDs."""
from pathlib import Path
import ast, copy, hashlib, json, os, shutil, signal, sqlite3, subprocess, sys, time
B = Path("/mnt/sdb/home/lizh639")
T = B / "tb2-hld-recuris50-20261020"
A = B / "appworld-hld-recuris70-20261020"


def read(p):
    return json.loads(p.read_text())


def save(p, d):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, indent=2))


def edit(s, old, new):
    assert old in s, old
    return s.replace(old, new)


def seal(root, names):
    r = read(root / "ready.json")
    for n in names:
        r["files"][n] = hashlib.sha256((root / n).read_bytes()).hexdigest()
    save(root / "ready.json", r)


def main():
    for root in (T, A):
        d = root / "concurrency6-20261020"
        d.mkdir(exist_ok=True)
        for n in ("ready.json", "health.json", "admissions.json", "effective_status.py"):
            if (root / n).exists() and not (d / (n + ".before")).exists():
                shutil.copy2(root / n, d / (n + ".before"))
    # Stop the idle transition helper only. Its solver/proxy owner remains alive.
    receipt = read(T / "resume-hld-20261020/launch-receipt.json")
    pid = receipt["pid"]
    status = read(T / "resume-hld-20261020/status.json")
    assert status["state"] == "waiting_for_current_trials"
    assert read(T / "health.json")["state"] == "draining"
    proc = Path(f"/proc/{pid}/cmdline")
    assert b"resume_hld_tb.py" in proc.read_bytes()
    os.kill(pid, signal.SIGTERM)
    save(T / "resume-hld-20261020/status.json", dict(
        state="superseded_by_concurrency6", reason="Start pending HLD without waiting for an unrelated running task"))

    # Freeze the exclusive pending-job set: the old controller is draining.
    h = read(T / "health.json")
    claims = []
    db = sqlite3.connect(f"file:{T/'spending.sqlite'}?mode=ro", uri=True)
    for row in h["rows"]:
        if row["state"] not in ("pending", "paused_by_user"):
            continue
        assert not (T / "jobs" / row["job"]).exists()
        assert db.execute("select count(*) from calls where job=?", (row["job"],)).fetchone()[0] == 0
        new = copy.deepcopy(row)
        new.update(state="pending", scheduling_owner="concurrency6-20261020")
        new.pop("pause_reason", None)
        claims.append(new)
    assert sum(r["arm"] == "hld" for r in claims) == 50
    db.close()
    save(T / "concurrency6-20261020/claims.json", claims)
    state = dict(state="prepared", rows=claims, active=[], phase="first",
                 supervisor_identity=None, spending=h["spending"])
    save(T / "concurrency6-20261020/admissions.json", state)

    # Retain the established task lifecycle, receipts, proxy and ledger logic.
    s = (T / "campaign.py").read_text()
    s = edit(s, "PORT=29051", "PORT=29151\nCONTROL=ROOT/'concurrency6-20261020'")
    s = edit(s, "atomic_json(ROOT/name,value)", "atomic_json(CONTROL/name,value)")
    s = edit(s, "with supervisor_lock(ROOT):", "with supervisor_lock(CONTROL):")
    for name in ("admissions.json", "control.json", "launch-once.marker"):
        s = s.replace("ROOT/'" + name + "'", "CONTROL/'" + name + "'")
    s = edit(s, "BudgetService(ROOT,port=29052)", "BudgetService(ROOT,port=29152)")
    s = edit(s, "if len(active)>=3:break", "if len(active)>=6:break")
    s = edit(s, ">= (1 if row['arm']=='hld' else 2)", ">= 3")
    s = edit(s, "candidates(rows,[v['row']['arm'] for v in active.values()])",
             "boost_candidates(rows,[v['row']['arm'] for v in active.values()])")
    s = edit(s, "total_concurrency=3", "total_concurrency=6")
    s = edit(s, "with (ROOT/name).open('xb')", "with (CONTROL/name).open('xb')")
    helpers = '''
def boost_candidates(rows, active_arms):
    busy=collections.Counter(active_arms)
    out=[]
    for row in rows:
        if sum(busy.values())>=6:break
        if row['state']=='pending' and busy[row['arm']]<3:
            out.append(row);busy[row['arm']]+=1
    return out

def space_ready(task, active):
    # Reserve the declared writable task capacity once; installed image layers
    # are already deducted from statvfs free bytes.
    tasks={x['name']:x for x in read(ROOT/'tasks.json')['tasks']}
    def allowance(name):
        e=tasks[name].get('environment',{})
        raw=str(e.get('storage','10G')).upper()
        value=float(raw.removesuffix('IB').removesuffix('B').removesuffix('G')) if raw.endswith(('G','GB','GIB')) else 10
        return max(6,value)*1024**3
    external=read(ROOT/'health.json').get('active',[])
    repair=read(ROOT/'infra-repair-20261020/health.json').get('active')
    other_count=len(external)+(1 if repair else 0)
    image=tasks[task].get('environment',{}).get('docker_image')
    cold=bool(image) and subprocess.run(['docker','image','inspect',image],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode!=0
    reserve=24*1024**3+allowance(task)+sum(allowance(x['row']['task']) for x in active.values())+other_count*10*1024**3+(20*1024**3 if cold else 0)
    return shutil.disk_usage('/var/lib/docker').free>=reserve and shutil.disk_usage(ROOT).free>=8*1024**3

'''
    s = edit(s, "if __name__=='__main__':", helpers + "\nif __name__=='__main__':")
    ast.parse(s)
    (T / "boost_campaign.py").write_text(s)
    # Extend aggregation by original job ID, preserving first attempts/repairs.
    s = (T / "effective_status.py").read_text()
    hook = '''    boost=read(R / "concurrency6-20261020/health.json")
    for x in boost.get("rows", []):
        if x["job"] in by_job:
            by_job[x["job"]].update(copy.deepcopy(x))
    h["boost"]={k:boost.get(k) for k in ("state","summary","active","updated_utc")}
    h["active"]=h.get("active",[])+boost.get("active",[])
    if boost.get("state") not in (None,"drained","finished"):
        h["state"]="running_boost"
        h["updated_utc"]=boost.get("updated_utc",h.get("updated_utc"))
'''
    s = edit(s, '    h["summary"] = summary(rows)', hook + '    h["summary"] = summary(rows)')
    (T / "effective_status.py").write_text(s)
    seal(T, ["boost_campaign.py", "effective_status.py"])

    s = (A / "resume_hld_app.py").read_text()
    start = s.index("def plan():")
    end = s.index("\ndef run_one(", start)
    plan = '''def plan():
    tasks=read(R/"task-manifest.json")["tasks"]
    done=[];queue=[]
    for row in tasks:
        rec=read(R/"jobs"/("recuris--"+row["task"])/"summary.json")
        assert rec.get("grading")=="complete"
        done.append(rec)
        original="hld--"+row["task"]
        prior=read(R/"jobs"/original/"summary.json")
        replacement=bool(prior.get("exclude_from_comparison"))
        job=original+"-resume1" if replacement else original
        latest=read(R/"jobs"/job/"summary.json")
        if latest:
            assert not latest.get("exclude_from_comparison")
            done.append(latest)
            continue
        assert not (R/"jobs"/job).exists(), "Unfinished admitted job requires reconciliation: "+job
        new=dict(row,_job=job,_budget_job=original)
        if replacement:new.update(_attempt=2,_rerun_of=original)
        queue.append(new)
    assert len(done)+len(queue)==140
    return done,queue
'''
    s = s[:start] + plan + s[end:]
    s = s.replace('resume-hld-20261020', 'concurrency6-20261020')
    s = edit(s, "ThreadPoolExecutor(max_workers=2)", "ThreadPoolExecutor(max_workers=6)")
    s = edit(s, "len(active) < 2", "len(active) < 6")
    s = edit(s, "concurrency=len(active),", "concurrency=len(active), concurrency_limit=6,")
    ast.parse(s)
    (A / "hld_app6.py").write_text(s)
    seal(A, ["hld_app6.py", "raise_app_concurrency.py"])
    save(B / "hld-recuris-expansion-20261020/concurrency6-plan.json", dict(
        tb_claimed=len(claims), tb_hld=50, tb_recuris=sum(x["arm"]=="recuris" for x in claims),
        tb_slots=6, app_slots=6, existing_tb_and_repair_continue=True,
        budget_reset=False, target_beijing="2026-10-21 08:00", automatic_new_campaigns=False))
    print("PREPARED", len(claims), "pending TB jobs")


if __name__ == "__main__":
    main()
