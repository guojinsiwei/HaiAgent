"""Resume the four mistakenly interrupted sessions without resetting their budget."""
from pathlib import Path
import concurrent.futures, copy, hashlib, inspect, json, os, shutil, subprocess, sys, time, uuid
import runner
from resume_clock import exclude_pause

R = runner.R
REC = R / "resume-interrupted-20261020"
JOBS = ["swp-10-old", "swp-10-new", "swp-11-old", "swp-11-new"]

def restore(name, job, folder, cwd, payload):
    original = R / "jobs" / job
    before = runner.read(REC / "original-health.json")["rows"][job]
    stop = runner.read(original / "user-stop.json")["time"]
    remaining = max(1, int(3000 - (stop - before["started"])))
    sessions = list((original / "live/dsh-home/sessions").glob("*/session-*"))
    assert len(sessions) == 1
    payload.update(session_id=sessions[0].name, remaining_wall=remaining)
    runner.run(["docker", "cp", str(original / "model.patch"), name + ":/tmp/resume.patch"])
    applied = runner.execute(name, f"cd {cwd} && git apply /tmp/resume.patch", 120, capture_output=True)
    assert applied.returncode == 0, "Saved patch could not be restored"
    stage = folder / "restore-live"
    shutil.copytree(original / "live", stage)
    # Copy only saved solver artifacts; no official grading output enters the solver.
    for lock in (stage / "dsh-home").rglob("session.lock"):
        lock.unlink()
    for stale in ["agent-exit.json", "wall-limit.json", "provider-stop.json"]:
        if (stage / stale).exists():
            (stage / stale).rename(stage / (stale + ".before-resume"))
    # The host deadline and the persisted HLD clock must exclude the same pause.
    # Only mutate the recovery copy; original checkpoints and usage stay intact.
    if list(stage.rglob("*.txn")):
        raise RuntimeError("Pending checkpoint transaction needs reconciliation")
    resumed_ms = int(time.time() * 1000)
    clock_receipts = []
    for checkpoint in stage.rglob("*.json"):
        saved = runner.read(checkpoint)
        if not isinstance(saved.get("full"), dict) or "startedAt" not in saved["full"]:
            continue
        adjusted = exclude_pause(saved, stop * 1000, resumed_ms, job + ":host-pause")
        clock_receipts.append(dict(path=str(checkpoint.relative_to(stage)),
                                   before_started_ms=saved["full"]["startedAt"],
                                   after_started_ms=adjusted["full"]["startedAt"]))
        runner.save(checkpoint, adjusted)
    if not clock_receipts:
        raise RuntimeError("No HLD task clock found; recovery would be unsafe")
    runner.save(folder / "pause-clock-receipt.json", dict(
        stopped_ms=stop * 1000, resumed_ms=resumed_ms, clocks=clock_receipts,
        original_checkpoints_unchanged=True, monetary_budget_reset=False))
    runner.execute(name, "mkdir -p /logs/agent", 30, check=True)
    runner.run(["docker", "cp", str(stage), name + ":/logs/agent/live"])
    runner.run(["docker", "cp", str(REC / "resume-entry.mjs"), name + ":/tmp/resume-entry.mjs"])
    runner.save(folder / "restoration.json", dict(
        original_job=job, original_session=sessions[0].name,
        patch_sha256=hashlib.sha256((original / "model.patch").read_bytes()).hexdigest(),
        remaining_wall_seconds=remaining, budget_job=job, budget_reset=False,
        resumed_from_saved_conversation=True, grader_feedback_provided=False,
    ))

def configure():
    source = inspect.getsource(runner.solve)
    source = source.replace("folder=R/'jobs'/job", "folder=REC/'jobs'/job")
    source = source.replace("name=LABEL+'-s-'+job", "name=LABEL+'-resume-'+job")
    source = source.replace("payload=payload_for(arm,job,instruction,budget,key)",
        "payload=payload_for(arm,job,instruction,budget,key)\n  restore(name,job,folder,cwd,payload)")
    source = source.replace("name,'/opt/node/bin/node','/opt/kz/container-run.mjs'",
        "name,'/opt/node/bin/node','/tmp/resume-entry.mjs'")
    assert "restore(name,job,folder,cwd,payload)" in source
    runner.REC = REC
    runner.restore = restore
    exec(compile(source, "resume-solve", "exec"), runner.__dict__)

def prepare():
    REC.mkdir(exist_ok=True)
    runner.freeze_validate()
    if not (REC / "original-health.json").exists():
        runner.save(REC / "original-health.json", runner.read(R / "health.json"))
    source = (R / "bundle/kz/container-run.mjs").read_text()
    source = source.replace("from './socket-relay.mjs'", "from '/opt/kz/socket-relay.mjs'")
    source = source.replace("from './deadline.mjs'", "from '/opt/kz/deadline.mjs'")
    source = source.replace("args.push('--json','-');", "args.push('--session-id',bundle.session_id,'--json','-');")
    source = source.replace("fs.openSync(logs+'/dsh.jsonl','wx')", "fs.openSync(logs+'/dsh.jsonl','a')")
    source = source.replace("fs.openSync(logs+'/dsh.stderr.log','wx')", "fs.openSync(logs+'/dsh.stderr.log','a')")
    source = source.replace("child.stdin.end(bundle.instruction)",
        "child.stdin.end('Continue the existing task from the saved conversation and current workspace. "
        "The previous process was interrupted by infrastructure. Retain existing work; inspect any "
        "unfinished tool operation before continuing. No external evaluation feedback is available.')")
    source = source.replace("deadline(child,3000,", "deadline(child,bundle.remaining_wall,")
    (REC / "resume-entry.mjs").write_text(source)
    runner.save(REC / "authorization.json", dict(
        reason="Correct assistant scope error; resume small HLD comparison",
        jobs=JOBS, original_budget_profile_unchanged=True,
        large_campaigns_hld_still_paused=True, source_algorithms_unchanged=True,
    ))

def main():
    prepare()
    configure()
    # Preserve the old supervisor's grading. Recovery uses a separate lock and
    # status until that supervisor exits, so neither writer overwrites the other.
    with runner.supervisor_lock(REC):
        original = runner.read(R / "health.json")
        original_pid = original.get("pid")
        runner.save(REC / "interrupted-grading-health.json", original)
        rows = copy.deepcopy(original["rows"])
        for job in JOBS:
            rows[job] = dict(task=rows[job]["task"], arm=rows[job]["arm"], state="pending",
                             continuation_of=job, interruption="assistant_scope_error")
        budget = runner.BudgetService(R, host="127.0.0.1", port=0)
        services = runner.Services(budget)
        key = runner.read(Path.home() / ".config/appworld-credentials/taotoken-standby.json")["key"]
        def checkpoint():
            with runner.STATE_LOCK:
                summary = {a: dict(
                    scored=sum(v["arm"] == a and v.get("official_score_valid") is True for v in rows.values()),
                    passed=sum(v["arm"] == a and v.get("official_score_valid") is True and v.get("reward") == 1 for v in rows.values()),
                    completed=sum(v["arm"] == a and v["state"] == "completed" for v in rows.values()),
                    engineering_failed=sum(v["arm"] == a and v["state"] == "engineering_failed" for v in rows.values()),
                ) for a in ["old", "new"]}
                active = sum(v["state"] not in ("completed", "engineering_failed") for v in rows.values())
                h = dict(state="running" if active else "finished", updated=time.time(), pid=os.getpid(),
                         rows=copy.deepcopy(rows), summary=summary, spending=budget.snapshot(),
                         concurrency=active, recovery_directory=str(REC), resumed_jobs=JOBS)
                targets = [REC / "health.json"]
                if not original_pid or not Path(f"/proc/{original_pid}").exists():
                    targets += [R / "health.json", R / "status.json"]
                for target in targets:
                    runner.save(target, h)
        tasks = {t["index"]: t for t in runner.read(R / "tasks.json")["tasks"]}
        for index in [10, 11]:
            tasks[index]["image_id"] = runner.read(R / "jobs" / f"swp-{index:02}-old" / "identity.json")["image_id"]
        try:
            checkpoint()
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                futures = [pool.submit(runner.solve, tasks[int(j.split("-")[1])], j.split("-")[2],
                                       services, budget, key, rows, checkpoint) for j in JOBS]
                while not all(f.done() for f in futures):
                    checkpoint()
                    time.sleep(5)
                for f in futures:
                    f.result()
        finally:
            checkpoint()
            services.close()
            budget.close()

if __name__ == "__main__":
    if "--prepare" in sys.argv:
        prepare()
        print("Prepared without model calls")
    elif "--launch" in sys.argv:
        prepare()
        with (REC / "launch.marker").open("x") as marker:
            marker.write(str(time.time()))
        with (REC / "controller.log").open("xb", buffering=0) as log:
            proc = subprocess.Popen([sys.executable, __file__], stdin=subprocess.DEVNULL,
                                    stdout=log, stderr=log, start_new_session=True)
        print(json.dumps(dict(pid=proc.pid, original_jobs=JOBS)))
    else:
        main()
