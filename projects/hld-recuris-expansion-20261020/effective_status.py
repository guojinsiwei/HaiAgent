"""Combine original attempts and explicit repairs without double-counting tasks."""
from pathlib import Path
import copy, json, sqlite3
from queue_policy import summary

R = Path(__file__).resolve().parent
def read(p):
    try:
        return json.loads(p.read_text())
    except (FileNotFoundError, ValueError):
        return {}

def status():
    h = copy.deepcopy(read(R / "health.json"))
    rows = h.get("rows", [])
    by_job = {x["job"]: x for x in rows}
    repair = read(R / "infra-repair-20261020/health.json")
    for x in repair.get("rows", []):
        original = by_job.get(x["original_job"])
        if original is None:
            continue
        original["original_state"] = original["state"]
        original["repair_job"] = x["job"]
        if x["state"] in ("done", "engineering_failure"):
            original.update(state=x["state"], result=x.get("result", {}),
                engineering_clean=x.get("result", {}).get("engineering_clean", False),
                repair_error=x.get("repair_error"))
        else:
            original["state"] = "repair_" + x["state"]
            original["engineering_clean"] = False
    score = read(R / "infra-repair-20261020/torch-regrade/result.json")
    if score.get("engineering_clean") and score.get("reward") in (0, 1):
        row = by_job["tb2hr50-09-recuris-torch-pipeline-parallelism"]
        row["original_state"] = row["state"]
        row.update(state="done", engineering_clean=True,
            result={**row.get("result", {}), "reward": score["reward"], "engineering_clean": True,
                    "scoring_recovered_from_snapshot": True, "paid_calls_in_regrade": 0})
    h["summary"] = summary(rows)
    h["repair"] = {k: repair.get(k) for k in ("state", "summary", "active", "updated")}
    h["active"] = h.get("active", []) + ([repair["active"]] if repair.get("active") else [])
    if repair.get("active"):
        h["state"] = "running_repair" if h.get("state") in ("drained", "finished") else h.get("state")
    if (R / "spending.sqlite").exists():
        with sqlite3.connect(f"file:{R/'spending.sqlite'}?mode=ro", uri=True, timeout=20) as db:
            settled, reserved, uncertain = db.execute(
                "select coalesce(sum(case when state='settled' then actual else 0 end),0),"
                "coalesce(sum(case when state='reserved' then reserved else 0 end),0),"
                "coalesce(sum(case when state='unknown' then reserved else 0 end),0) from calls").fetchone()
        b = h.setdefault("spending", {})
        b.update(settled_microcny=settled, reserved_microcny=reserved, uncertain_microcny=uncertain)
        b["remaining_microcny"] = b.get("limit_microcny", 800000000) - settled - reserved - uncertain
    return h

if __name__ == "__main__":
    print(json.dumps(status(), indent=2))
