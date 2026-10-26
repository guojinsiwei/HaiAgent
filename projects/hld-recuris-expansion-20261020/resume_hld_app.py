"""Resume only the authorized HLD arm, retaining Recuris and prior clean results."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import fcntl, json, os, shutil, sys, time
from runner import R, read, save, trial
from app_campaign import validate
from app_preflight import ensure
from spending import Ledger


def plan():
    tasks = read(R / "task-manifest.json")["tasks"]
    done, queue = [], []
    for row in tasks:
        task = row["task"]
        rec = read(R / "jobs" / ("recuris--" + task) / "summary.json")
        assert rec.get("grading") == "complete", task
        done.append(rec)
        original = "hld--" + task
        prior = read(R / "jobs" / original / "summary.json")
        if prior and not prior.get("exclude_from_comparison"):
            assert prior.get("grading") == "complete" and not prior.get("engineering_fault")
            done.append(prior)
            continue
        new = dict(row)
        if prior:
            assert prior.get("user_interrupted") and prior.get("engineering_fault")
            new.update(_job=original + "-resume1", _budget_job=original,
                       _attempt=2, _rerun_of=original)
        else:
            assert not (R / "jobs" / original).exists()
            new["_job"] = original
            new["_budget_job"] = original
        assert not (R / "jobs" / new["_job"]).exists(), "Attempt already exists"
        queue.append(new)
    assert len(done) + len(queue) == 140
    assert len(queue) == 69
    return done, queue


def run_one(row, key, ledger):
    ensure(row)
    return trial(row, key, "hld", ledger)


def main():
    profile = validate()
    key = read(Path.home() / ".config/appworld-credentials/taotoken-standby.json")["key"]
    with (R / "supervisor.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        (R / "resume-hld-20261020/started.marker").open("x").write(str(time.time()))
        done, queue = plan()
        ledger = Ledger(R / "spending.sqlite", profile)
        active = {}
        held = False

        def checkpoint():
            summary = {}
            for arm in ("hld", "recuris"):
                rows = [x for x in done if x.get("arm") == arm]
                summary[arm] = dict(total=70, finished=len(rows),
                                    scored=sum(x.get("grading") == "complete" for x in rows),
                                    passed=sum(x.get("official_success") is True for x in rows),
                                    engineering_faults=sum(bool(x.get("engineering_fault")) for x in rows))
            h = dict(state="held_provider" if held else "running" if active else
                     "waiting_for_storage" if queue else "complete",
                     updated=time.time(), pid=os.getpid(), concurrency=len(active),
                     enabled_arms=["hld", "recuris"], paused_arms=[], completed=done,
                     active=[dict(task=r["task"], arm="hld", job=r["_job"],
                                  budget_job=r["_budget_job"]) for r in active.values()],
                     pending=[dict(task=r["task"], arm="hld", job=r["_job"]) for r in queue],
                     summary=summary, budget=ledger.status(),
                     recovery="resume-hld-20261020", automatic_paid_retries=False)
            save(R / "admissions.json", h)
            save(R / "health.json", h)
            save(R / "resume-hld-20261020/health.json", h)
            return h

        with ThreadPoolExecutor(max_workers=2) as pool:
            while queue or active:
                for future in list(active):
                    if not future.done():
                        continue
                    row = active.pop(future)
                    try:
                        result = future.result()
                    except Exception as exc:
                        result = dict(job=row["_job"], budget_job=row["_budget_job"],
                                      arm="hld", task=row["task"], state="needs_attention",
                                      engineering_fault=type(exc).__name__)
                    done.append(result)
                    if any(x in (401, 402, 403) for x in result.get("http_errors", [])):
                        held = True
                budget = ledger.status()
                if budget["halt_reason"]:
                    held = True
                if held and not active:
                    checkpoint()
                    return
                while queue and len(active) < 2 and not held:
                    if shutil.disk_usage("/var/lib/docker").free < 24 * 2**30 or shutil.disk_usage(R).free < 8 * 2**30:
                        break
                    row = queue.pop(0)
                    save(R / "admitted" / (row["_job"] + ".json"), dict(
                        task=row["task"], arm="hld", job=row["_job"],
                        budget_job=row["_budget_job"], time=time.time(),
                        automatic_paid_retry=False, source="user_resume_new_hld"))
                    active[pool.submit(run_one, row, key, ledger)] = row
                checkpoint()
                if active or queue:
                    time.sleep(5)
        save(R / "summary.json", checkpoint())


if __name__ == "__main__":
    if "--check" in sys.argv:
        validate()
        done, queue = plan()
        print(json.dumps(dict(retained=len(done), pending=len(queue),
                              shared_budget_restarts=sum(r.get("_attempt") == 2 for r in queue))))
    else:
        main()
