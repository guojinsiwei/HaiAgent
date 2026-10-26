"""Read public official manifests over the workstation's reachable network."""
import concurrent.futures
import hashlib
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "manifests"
TASKS = [x["name"] for x in json.loads((ROOT.parent/"tasks.json").read_text())["tasks"]]


def fetch(task):
    repo = "alexgshaw/" + task
    url = "https://registry-1.docker.io/v2/" + repo + "/manifests/20251031"
    for attempt in range(4):
        try:
            with urllib.request.urlopen(
                "https://auth.docker.io/token?service=registry.docker.io&scope=repository:"
                + repo + ":pull", timeout=30
            ) as response:
                token = json.load(response)["token"]
            request = urllib.request.Request(url, headers={
                "Authorization": "Bearer " + token,
                "Accept": "application/vnd.docker.distribution.manifest.v2+json",
            })
            with urllib.request.urlopen(request, timeout=45) as response:
                raw = response.read()
                digest = response.headers["Docker-Content-Digest"]
            assert digest == "sha256:" + hashlib.sha256(raw).hexdigest()
            assert json.loads(raw)["schemaVersion"] == 2
            (ROOT / (task + ".manifest.json")).write_bytes(raw)
            record = dict(task=task, image=repo + ":20251031", digest=digest,
                          source=url, header_verified=True, time=time.time())
            (ROOT / (task + ".source.json")).write_text(json.dumps(record, indent=2))
            return record
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2 * (attempt + 1))

if __name__ == "__main__":
    ROOT.mkdir(exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        for result in pool.map(fetch, sys.argv[1:] or TASKS):
            print(json.dumps(result), flush=True)
