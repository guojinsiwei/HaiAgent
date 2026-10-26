"""Resume the drained main queue once real offline repair checks have passed."""
from pathlib import Path
import json, subprocess, time
from recovery import owned_alive
from storage import atomic_json
R = Path(__file__).resolve().parent
A = R / "infra-repair-20261020"
def read(p):
    try: return json.loads(p.read_text())
    except (FileNotFoundError, ValueError): return {}
def main():
    while True:
        h = read(R / "health.json")
        checked = read(A / "preflight-results.json")
        if checked and not checked.get("all_passed"):
            atomic_json(A/"main-resume.json", dict(state="held_failed_repair_preflight"))
            return
        if checked.get("all_passed") and h.get("state") == "drained" and not owned_alive(h.get("supervisor_identity")):
            break
        atomic_json(A/"main-resume.json", dict(state="waiting_for_preflight_and_drain", updated=time.time()))
        time.sleep(10)
    key = read(Path.home()/".config/appworld-credentials/taotoken-standby.json")["key"]
    p = subprocess.run([str(R/"venv/bin/python"), str(R/"campaign.py"), "--resume"],
        input=json.dumps({"key": key})+"\n", capture_output=True, text=True, timeout=90)
    atomic_json(A/"main-resume.json", dict(state="resumed" if p.returncode==0 else "resume_failed",
        updated=time.time(), exit_code=p.returncode, stdout=p.stdout, stderr=p.stderr[-2000:]))
if __name__ == "__main__": main()
