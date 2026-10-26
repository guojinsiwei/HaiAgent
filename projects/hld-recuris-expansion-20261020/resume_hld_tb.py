"""Wait for admitted Recuris tasks, then resume the existing paired queue."""
from pathlib import Path
import hashlib, json, os, subprocess, sys, time
R = Path(__file__).resolve().parent
sys.path.insert(0, str(R))
import campaign
from recovery import owned_alive


def main():
    record = R / "resume-hld-20261020"
    record.mkdir(exist_ok=True)
    (record / "coordinator.marker").open("x").write(str(time.time()))
    h = campaign.read(R / "health.json")
    identity = h.get("supervisor_identity")
    campaign.save("control.json", dict(command="drain", supervisor_identity=identity,
                                      reason="user_resume_new_hld_after_active_trials"))
    campaign.save("resume-hld-20261020/status.json", dict(
        state="waiting_for_current_trials", old_supervisor=identity, active=h.get("active")))
    while owned_alive(identity):
        time.sleep(5)
    # Reconcile only when no old supervisor or its trials own admissions.
    campaign.validate()
    state, problems = campaign.reconcile(R, campaign.read(R / "admissions.json"), campaign.trial)
    if problems:
        raise RuntimeError(str(problems))
    campaign.save("resume-hld-20261020/before-admissions.json", state)
    for row in state["rows"]:
        if row["arm"] == "hld":
            assert row["state"] == "paused_by_user"
            assert not (R / "jobs" / row["job"]).exists()
            row.update(state="pending", resume_reason="user_new_hld_large_comparison")
            row.pop("pause_reason", None)
    campaign.save("admissions.json", state)
    campaign.save("health.json", state)
    key = campaign.read(Path.home() / ".config/appworld-credentials/taotoken-standby.json")["key"]
    p = subprocess.run([campaign.PY, str(R / "campaign.py"), "--resume"],
                       input=json.dumps(dict(key=key)), text=True, capture_output=True)
    if p.returncode:
        raise RuntimeError(p.stderr[-1500:].replace(key, "[REDACTED]"))
    receipt = json.loads(p.stdout.strip().splitlines()[-1])
    campaign.save("resume-hld-20261020/status.json", dict(
        state="resumed", receipt=receipt, hld_tasks=50, max_hld_concurrency=1,
        budget_reset=False))
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()
