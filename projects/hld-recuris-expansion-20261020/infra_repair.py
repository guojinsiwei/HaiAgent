"""One-slot, explicitly authorized repair of zero-paid-call image preflight failures."""
from pathlib import Path
import copy, datetime, json, os, secrets, sqlite3, subprocess, sys, threading, time, uuid
import campaign
from spending import BudgetService
from storage import atomic_json, supervisor_lock
from recovery import completed_attempt, process_identity

R = Path(__file__).resolve().parent
A = R / "infra-repair-20261020"

def read(p):
    return campaign.read(p)

def spent_calls(job):
    with sqlite3.connect(R / "spending.sqlite", timeout=20) as db:
        return db.execute("select count(*) from calls where job=?", (job,)).fetchone()[0]

def plan():
    failures = read(A / "original-failures.json")
    assert len(failures) >= 5
    out = []
    for x in failures:
        assert x["arm"] == "recuris" and x.get("admission_offline") is True
        assert x["result"].get("reason") in ("preflight_failed", "result_collection_error")
        out.append(dict(task=x["task"], arm="recuris", stage="image-repair",
            job=x["job"] + "-infra1", budget_job=x["job"], original_job=x["job"], state="pending"))
    return out

def run():
    campaign.validate()
    with supervisor_lock(A):
        assert not (A / "admissions.json").exists(), "No implicit replay of repair admissions"
        rows = plan()
        for x in rows:
            assert spent_calls(x["original_job"]) == 0, "Original job already consumed model calls"
        active = None
        def checkpoint(state="running"):
            atomic_json(A / "admissions.json", dict(state=state, updated=time.time(),
                supervisor_identity=process_identity(os.getpid()), rows=copy.deepcopy(rows),
                active=active, concurrency=1 if active else 0,
                summary=dict(preflight_passed=sum(bool(x.get("preflight_ok")) for x in rows),
                    scored=sum(x.get("result", {}).get("reward") in (0, 1) for x in rows),
                    passed=sum(x.get("result", {}).get("reward") == 1 for x in rows),
                    failed=sum(x["state"] == "engineering_failure" for x in rows)),
                original_budget_ledger=str(R / "spending.sqlite"), no_paid_replay=True))
            atomic_json(A / "health.json", read(A / "admissions.json"))
        def attempt(row, offline, key=None, budget=None, proxy_url=None):
            nonlocal active
            # Read-only capacity admission. Existing experiment processes keep running.
            while not campaign.space_ready(row["task"], {}):
                row["state"] = "waiting_for_storage"
                checkpoint()
                time.sleep(10)
            attempt_id = uuid.uuid4().hex
            row["preflight_attempt_id" if offline else "attempt_id"] = attempt_id
            row["admission_offline"] = offline
            row["state"] = "preflighting" if offline else "running"
            active = dict(job=row["job"], task=row["task"], offline=offline)
            checkpoint()
            env = {k:v for k,v in os.environ.items()
                   if k != "TAOTOKEN_API_KEY" and not k.startswith("CAMPAIGN_BUDGET_")}
            env.update(PYTHONPATH=str(R)+":"+str(R/"dependencies"), PYTHONDONTWRITEBYTECODE="1",
                PAIRED_TASK=row["task"], PAIRED_ATTEMPT_ID=attempt_id)
            if not offline:
                assert spent_calls(row["original_job"]) == 0, "Refusing paid replay"
                env.update(TAOTOKEN_API_KEY=key, PAIRED_PROXY_URL=proxy_url,
                    CAMPAIGN_BUDGET_REQUIRED="1", CAMPAIGN_BUDGET_URL=budget.url,
                    CAMPAIGN_BUDGET_TOKEN=budget.token, CAMPAIGN_BUDGET_JOB=row["budget_job"],
                    CAMPAIGN_BUDGET_ARM="dsh")
            with (A / (("preflight-" if offline else "") + row["job"] + ".log")).open("xb", buffering=0) as log:
                proc = subprocess.Popen(campaign.command(row, offline), env=env,
                    stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
                active["pid"] = proc.pid
                while proc.poll() is None:
                    if not offline:
                        row["live"] = campaign.live_snapshot(row)
                    checkpoint()
                    time.sleep(5)
                code = proc.returncode
            active = None
            assert completed_attempt(R, row, offline), "Missing completed runner receipt"
            result = campaign.trial(row, offline)
            result["harbor_exit"] = code
            if code:
                result["engineering_clean"] = False
            if offline:
                row["preflight"] = result
                row["preflight_ok"] = bool(result["engineering_clean"])
                row["state"] = "preflight_passed" if row["preflight_ok"] else "engineering_failure"
                assert spent_calls(row["original_job"]) == 0, "Offline preflight consumed calls"
            else:
                row["result"] = result
                row["state"] = "done" if result["engineering_clean"] else "engineering_failure"
            checkpoint()
        checkpoint("preflighting")
        for row in rows:
            try:
                attempt(row, True)
            except Exception as error:
                active = None
                row.update(state="engineering_failure", repair_error=type(error).__name__ + ": " + str(error)[:300])
                checkpoint()
        atomic_json(A / "preflight-results.json", dict(model_calls=0,
            all_passed=all(x.get("preflight_ok") for x in rows), rows=rows))
        # Only verified tasks advance; a failed task does not prevent the others.
        key = read(Path.home() / ".config/appworld-credentials/taotoken-standby.json")["key"]
        proxy_module = campaign.proxy_module()
        proxy = proxy_module.ThreadingHTTPServer((proxy_module.HOST, 0), proxy_module.Handler)
        threading.Thread(target=proxy.serve_forever, daemon=True).start()
        budget = BudgetService(R, host=proxy_module.HOST, port=0)
        budget.url = f"http://{proxy_module.HOST}:{budget.server.server_port}"
        try:
            for row in rows:
                if not row.get("preflight_ok"):
                    continue
                try:
                    attempt(row, False, key, budget, f"http://{proxy_module.HOST}:{proxy.server_port}")
                except Exception as error:
                    active = None
                    row.update(state="engineering_failure", repair_error=type(error).__name__ + ": " + str(error)[:300])
                    checkpoint()
            checkpoint("finished")
        finally:
            proxy.shutdown()
            proxy.server_close()
            budget.close()

if __name__ == "__main__":
    if "--launch" in sys.argv:
        campaign.validate()
        with (A / "launch.marker").open("x") as f:
            f.write(str(time.time()))
        with (A / "controller.log").open("xb", buffering=0) as log:
            p = subprocess.Popen([sys.executable, __file__], stdin=subprocess.DEVNULL,
                stdout=log, stderr=log, start_new_session=True)
        print(json.dumps(dict(pid=p.pid, tasks=len(plan()), workers=1, reuse_original_budget=True)))
    else:
        run()
