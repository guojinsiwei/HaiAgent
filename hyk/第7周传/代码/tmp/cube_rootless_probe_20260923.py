"""Nonpersistent namespace checks; no daemon, mount, installation or resource creation."""
import json
from pathlib import Path
import shutil
import socket
import subprocess

result = {"host": socket.gethostname(), "tools": {}, "namespace_checks": {}}
for name in ("newuidmap", "newgidmap", "slirp4netns", "pasta", "runc", "crun", "skopeo", "fuse-overlayfs"):
    result["tools"][name] = shutil.which(name)
for path in ("/etc/subuid", "/etc/subgid"):
    file = Path(path)
    result[path] = {"exists": file.exists(), "root_mapping_configured":
                   file.exists() and any(line.startswith(("root:", "0:"))
                                          for line in file.read_text().splitlines())}
checks = {
    "user_mount": ["--user", "--map-root-user", "--mount"],
    "user_network": ["--user", "--map-root-user", "--net"],
    "user_pid": ["--user", "--map-root-user", "--pid", "--fork"],
    "combined": ["--user", "--map-root-user", "--mount", "--net", "--pid", "--fork", "--uts", "--ipc"],
}
for name, flags in checks.items():
    try:
        run = subprocess.run(["unshare", *flags, "true"], capture_output=True, text=True, timeout=5)
        result["namespace_checks"][name] = {"return_code": run.returncode, "error": run.stderr.strip()[:220]}
    except (OSError, subprocess.TimeoutExpired) as error:
        result["namespace_checks"][name] = {"error_type": type(error).__name__}
for name in ("/proc/sys/user/max_user_namespaces", "/proc/sys/kernel/unprivileged_userns_clone"):
    if Path(name).is_file():
        result[name] = Path(name).read_text().strip()
print(json.dumps(result, indent=2))
