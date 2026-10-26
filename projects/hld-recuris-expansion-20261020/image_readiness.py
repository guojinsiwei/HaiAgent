"""Pin and cache official task images before Harbor admission, without model keys."""
from pathlib import Path
import fcntl, hashlib, json, os, shutil, subprocess, time
from storage import atomic_json

R = Path(__file__).resolve().parent

def read(path):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, ValueError):
        return {}

def local(image):
    p = subprocess.run(["docker", "image", "inspect", image], capture_output=True, text=True, timeout=30)
    if p.returncode:
        return None
    return json.loads(p.stdout)[0]

def ensure(task):
    rows = read(R / "tasks.json")["tasks"]
    spec = next(x for x in rows if x["name"] == task)
    image = spec.get("environment", {}).get("docker_image")
    if not image:
        return {"task": task, "state": "official_build_required"}
    folder = R / "image-cache" / task
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / "lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        cached = local(image)
        previous = read(folder / "ready.json")
        if cached:
            if previous and previous["image_id"] != cached["Id"]:
                raise RuntimeError("Cached task image identity changed: " + task)
            result = previous or dict(task=task, image=image, image_id=cached["Id"],
                source="existing_local_image", repo_digests=cached.get("RepoDigests", []), ready=True)
            atomic_json(folder / "ready.json", result)
            return result
        # Keep the existing low-space policy; never prune shared images here.
        if shutil.disk_usage("/var/lib/docker").free < 24 * 2**30:
            raise RuntimeError("Insufficient storage for image preparation")
        env = {k:v for k,v in os.environ.items()
               if not any(s in k.upper() for s in ("API_KEY", "AUTH_TOKEN", "CAMPAIGN_BUDGET"))}
        qualified = image if "." in image.split("/")[0] or ":" in image.split("/")[0] else "docker.io/" + image
        reference = "docker://" + qualified
        pin = read(folder / "source.json")
        if not pin:
            last = None
            for attempt in range(3):
                try:
                    # --raw avoids downloading the config blob through the failing CDN.
                    p = subprocess.run(["skopeo", "inspect", "--raw", reference],
                        env=env, capture_output=True, timeout=90, check=True)
                    manifest = json.loads(p.stdout)
                    assert manifest.get("schemaVersion") == 2
                    digest = "sha256:" + hashlib.sha256(p.stdout).hexdigest()
                    pin = dict(image=image, digest=digest, time=time.time())
                    atomic_json(folder / "source.json", pin)
                    break
                except (subprocess.SubprocessError, AssertionError) as error:
                    last = error
                    if attempt < 2:
                        time.sleep(2 ** attempt)
            if not pin:
                raise RuntimeError("Image manifest download failed: " + task) from last
        repository = qualified.rsplit("@", 1)[0]
        if ":" in repository.rsplit("/", 1)[-1]:
            repository = repository.rsplit(":", 1)[0]
        pinned = "docker://" + repository + "@" + pin["digest"]
        mirror = pinned.replace("docker://docker.io/", "docker://dockerproxy.net/")
        sources = [mirror, pinned, mirror] if mirror != pinned else [pinned] * 3
        with (folder / "download.log").open("ab", buffering=0) as log:
            for attempt in range(1, 4):
                atomic_json(folder / "status.json", dict(state="downloading", attempt=attempt, time=time.time()))
                try:
                    source = sources[attempt - 1]
                    # The mirror must serve the exact manifest pinned at the official origin.
                    manifest = subprocess.run(["skopeo", "inspect", "--raw", source],
                        env=env, capture_output=True, timeout=90, check=True).stdout
                    if "sha256:" + hashlib.sha256(manifest).hexdigest() != pin["digest"]:
                        raise RuntimeError("Mirror manifest differs from official origin")
                    subprocess.run(["skopeo", "copy", "--retry-times", "3", "--override-os", "linux",
                        "--override-arch", "amd64", source, "docker-daemon:" + image],
                        env=env, stdout=log, stderr=log, timeout=1800, check=True)
                    cached = local(image)
                    if not cached or cached["Architecture"] != "amd64" or cached["Os"] != "linux":
                        raise RuntimeError("Downloaded image could not be verified")
                    if previous and previous["image_id"] != cached["Id"]:
                        raise RuntimeError("Restored task image identity differs from original")
                    result = dict(task=task, image=image, image_id=cached["Id"],
                        source_digest=pin["digest"], transport=source.split("/")[2],
                        source="skopeo_digest_pinned", ready=True)
                    atomic_json(folder / "ready.json", result)
                    atomic_json(folder / "status.json", dict(state="ready", time=time.time()))
                    return result
                except subprocess.SubprocessError:
                    if attempt == 3:
                        atomic_json(folder / "status.json", dict(state="download_failed", time=time.time()))
                        raise
                    time.sleep(3 * attempt)

if __name__ == "__main__":
    import sys
    for task in sys.argv[1:]:
        print(json.dumps(ensure(task)), flush=True)
