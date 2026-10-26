"""Admission-only resource sharing. Existing trials are never interrupted."""
import collections
import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONTROL = "capacity10-20261020"

def read(path):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, ValueError):
        return {}

def app_finished():
    h = read(ROOT.parent / "appworld-hld-recuris70-20261020/health.json")
    return h.get("state") == "complete" and not h.get("active") and all(
        h.get("summary", {}).get(a, {}).get("scored") == 70 for a in ("hld", "recuris"))

def external_rows(owner=CONTROL):
    result = {}
    for folder in ("concurrency6-20261020", CONTROL,
                   "infra-repair3-20261020", "infra-repair5-20261020"):
        if folder == owner:
            continue
        h = read(ROOT / folder / "health.json")
        active = h.get("active", [])
        if isinstance(active, dict):
            active = [active]
        for row in active or []:
            result[row["job"]] = dict(
                job=row["job"], task=row.get("task"),
                arm="hld" if "-hld-" in row["job"] else "recuris")
        # Each repair controller has one worker; reserve its next admission too.
        if folder.startswith("infra-repair") and h.get("state") != "finished" and not active:
            if (ROOT / folder / "original-failures.json").exists():
                result[folder] = dict(job=folder, task=None, arm="recuris")
    return list(result.values())

def choose(rows, active_arms, external):
    busy = collections.Counter(active_arms + [x["arm"] for x in external])
    # HLD gets seven slots while Recuris remains; unused Recuris slots are lent to HLD.
    recuris_waiting = any(x["arm"] == "recuris" and x["state"] == "pending" for x in rows)
    hld_limit = 7 if recuris_waiting or busy["recuris"] else 10
    result = []
    for row in sorted(rows, key=lambda x: x["arm"] != "hld"):
        if sum(busy.values()) >= 10:
            break
        limit = hld_limit if row["arm"] == "hld" else 3
        if row["state"] == "pending" and busy[row["arm"]] < limit:
            result.append(row)
            busy[row["arm"]] += 1
    return result

def space_ready(task, active, owner=CONTROL):
    if not app_finished():
        return False
    other = external_rows(owner)
    local = [x["row"] for x in active.values()]
    if len(other) + len(local) >= 10:
        return False
    tasks = {x["name"]: x for x in read(ROOT / "tasks.json")["tasks"]}
    image = tasks[task].get("environment", {}).get("docker_image")
    cold = bool(image) and subprocess.run(
        ["docker", "image", "inspect", image], stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, timeout=20).returncode != 0
    # Every task in this frozen cohort declares 10 GiB writable capacity.
    assert all(x.get("environment", {}).get("storage") == "10G" for x in tasks.values())
    reserve = (24 + 10 * (len(other) + len(local) + 1) + (20 if cold else 0)) * 2**30
    memory = dict(line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines())
    available = int(memory["MemAvailable"].split()[0]) * 1024
    return (shutil.disk_usage("/var/lib/docker").free >= reserve
            and shutil.disk_usage(ROOT).free >= 8 * 2**30
            and available >= 24 * 2**30
            and os.getloadavg()[0] < (os.cpu_count() or 1) * 0.8)
