"""Read-only own-container and own-namespace capability check; never prints credentials."""
import json
import os
from pathlib import Path
import shutil
import socket
import ssl
import subprocess
import urllib.error
import urllib.request

report = {"host": socket.gethostname(), "uid": os.getuid(), "mutations": False}
report["tools"] = {name: shutil.which(name) for name in (
    "docker", "dockerd", "podman", "nerdctl", "kubectl", "apptainer", "singularity",
    "buildah", "rootlesskit", "unshare")}
report["runtime_sockets"] = {name: Path(name).is_socket() for name in (
    "/var/run/docker.sock", "/run/containerd/containerd.sock", "/run/podman/podman.sock")}
status = {}
for line in Path("/proc/self/status").read_text().splitlines():
    key, _, value = line.partition(":")
    if key in {"CapEff", "CapBnd", "NoNewPrivs", "Seccomp"}:
        status[key] = value.strip()
report["process_security"] = status
caps = int(status.get("CapEff", "0"), 16)
report["capabilities"] = {"SYS_ADMIN": bool(caps & (1 << 21)),
                          "NET_ADMIN": bool(caps & (1 << 12)),
                          "SYS_CHROOT": bool(caps & (1 << 18))}
if report["tools"]["unshare"]:
    try:
        check = subprocess.run([report["tools"]["unshare"], "--user", "--map-root-user", "true"],
                               capture_output=True, text=True, timeout=5)
        report["rootless_user_namespace"] = {"return_code": check.returncode,
                                            "error": check.stderr.strip()[:250]}
    except subprocess.TimeoutExpired:
        report["rootless_user_namespace"] = {"status": "timeout"}
report["mount_types"] = sorted({line.split(" - ", 1)[1].split()[0]
                               for line in Path("/proc/self/mountinfo").read_text().splitlines()
                               if " - " in line})
for name in ("/sys/fs/cgroup", "/dev/fuse", "/dev/kvm"):
    report.setdefault("local_paths", {})[name] = {"exists": Path(name).exists(),
                                                 "writable": os.access(name, os.W_OK)}

service = Path("/var/run/secrets/kubernetes.io/serviceaccount")
if (service / "token").is_file():
    namespace = (service / "namespace").read_text().strip()
    token = (service / "token").read_text().strip()
    host = os.environ.get("KUBERNETES_SERVICE_HOST", "kubernetes.default.svc")
    port = os.environ.get("KUBERNETES_SERVICE_PORT_HTTPS", "443")
    api = "https://" + host + ":" + port
    context = ssl.create_default_context(cafile=str(service / "ca.crt"))
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                         urllib.request.HTTPSHandler(context=context))
    report["kubernetes"] = {"namespace": namespace, "access_reviews": []}
    # SelfSubjectAccessReview asks whether access is allowed; it creates no Pod,
    # Job, service, or persistent resource and does not use another identity.
    for group, resource, verb, subresource in (
        ("", "pods", "get", None), ("", "pods", "list", None),
        ("", "pods", "create", None), ("", "pods", "delete", None),
        ("", "pods", "create", "exec"),
        ("batch", "jobs", "create", None), ("batch", "jobs", "get", None),
        ("batch", "jobs", "delete", None),
        ("apps", "deployments", "create", None),
    ):
        attributes = {"namespace": namespace, "group": group, "resource": resource, "verb": verb}
        if subresource:
            attributes["subresource"] = subresource
        payload = {"apiVersion": "authorization.k8s.io/v1", "kind": "SelfSubjectAccessReview",
                   "spec": {"resourceAttributes": attributes}}
        request = urllib.request.Request(api + "/apis/authorization.k8s.io/v1/selfsubjectaccessreviews",
                    data=json.dumps(payload).encode(), method="POST",
                    headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
        outcome = {"resource": resource + ("/" + subresource if subresource else ""), "verb": verb}
        try:
            with opener.open(request, timeout=10) as response:
                result = json.load(response).get("status", {})
            outcome.update(allowed=result.get("allowed"), denied=result.get("denied"),
                           evaluation_error=bool(result.get("evaluationError")))
        except urllib.error.HTTPError as error:
            outcome.update(http_status=error.code, allowed=None)
        except (urllib.error.URLError, OSError, ValueError):
            outcome.update(status="connection_or_response_error", allowed=None)
        report["kubernetes"]["access_reviews"].append(outcome)
    token = None
print(json.dumps(report, ensure_ascii=True, indent=2))
