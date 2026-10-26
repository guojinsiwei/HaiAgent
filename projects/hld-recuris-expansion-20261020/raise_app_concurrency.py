"""Drain only admissions through preflight locks, then resume with six workers."""
from pathlib import Path
import fcntl, hashlib, json, os, signal, subprocess, sys, time
R = Path(__file__).resolve().parent
sys.path.insert(0, str(R))
from runner import read, save


def main():
    out = R / "concurrency6-20261020"
    out.mkdir(exist_ok=True)
    (out / "transition.marker").open("x").write(str(time.time()))
    before = read(R / "health.json")
    old_pid = before["pid"]
    command = Path(f"/proc/{old_pid}/cmdline").read_bytes()
    assert b"resume_hld_app.py" in command
    held = []
    gated_tasks = set()
    try:
        # Acquire future task gates without blocking any currently active task.
        active_tasks = {x["task"] for x in before.get("active", [])}
        for row in read(R / "task-manifest.json")["tasks"]:
            if row["task"] in active_tasks:
                continue
            p = R / "preflight" / row["task"] / "lock"
            p.parent.mkdir(parents=True, exist_ok=True)
            f = p.open("a")
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                held.append(f)
                gated_tasks.add(row["task"])
            except BlockingIOError:
                f.close()
        save(out / "status.json", dict(state="draining_active_trials", old_pid=old_pid))
        while True:
            current = read(R / "health.json")
            assert current["pid"] == old_pid
            unfinished = []
            for x in current.get("active", []):
                d = R / "jobs" / x["job"]
                if d.exists() and not (d / "summary.json").exists():
                    unfinished.append(x["job"])
            if not unfinished and all(
                x["task"] in gated_tasks or
                (R / "jobs" / x["job"] / "summary.json").exists()
                for x in current.get("active", [])
            ):
                # A dispatched future can only create its directory after ensure().
                # Gate every active future before stopping its waiting supervisor.
                assert all(not (R / "jobs" / x["job"]).exists() or
                           (R / "jobs" / x["job"] / "summary.json").exists()
                           for x in current.get("active", []))
                break
            time.sleep(5)
        save(out / "before-transition.json", current)
        assert Path(f"/proc/{old_pid}/cmdline").read_bytes() == command
        os.kill(old_pid, signal.SIGTERM)
        for _ in range(60):
            if not Path(f"/proc/{old_pid}").exists():
                break
            stat = Path(f"/proc/{old_pid}/stat").read_text().rsplit(")", 1)[1].split()
            if stat[0] == "Z":
                break
            time.sleep(1)
        else:
            raise RuntimeError("Old controller did not exit")
    finally:
        for f in held:
            f.close()
    with (out / "controller.log").open("xb", buffering=0) as log:
        p = subprocess.Popen([sys.executable, "-u", str(R / "hld_app6.py")],
                             cwd=R, stdin=subprocess.DEVNULL,
                             stdout=log, stderr=log, start_new_session=True)
    time.sleep(3)
    if p.poll() is not None:
        raise RuntimeError("Six-worker controller failed; inspect its log")
    save(out / "status.json", dict(state="running", pid=p.pid, concurrency_limit=6,
                                   paid_work_interrupted=False, budget_reset=False))


if __name__ == "__main__":
    main()
