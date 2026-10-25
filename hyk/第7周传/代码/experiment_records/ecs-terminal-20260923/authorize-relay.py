"""Apply ONLY after user approval of the scoped cloud relay access."""
from pathlib import Path
import os

target = Path("/home/ecs-user/.ssh/authorized_keys")
marker = "terminalbench-download-relay-20260923"
public_key = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIBvGdx1V/AuQDyi01a58V+HIb3weqGOF3Qjh71EVAkVl " + marker
entry = 'from="154.213.1.67",restrict,port-forwarding,permitopen="127.0.0.1:1",permitlisten="127.0.0.1:28761",command="/bin/false" ' + public_key
original = target.read_text()
existing = [line for line in original.splitlines() if marker in line]
if existing:
    if existing != [entry]:
        raise SystemExit("Existing relay authorization differs; refusing to overwrite")
else:
    backup = target.with_name("authorized_keys.before-terminal-relay-20260923")
    if not backup.exists():
        fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as stream:
            stream.write(original)
    with target.open("a") as stream:
        stream.write(("" if original.endswith("\n") else "\n") + entry + "\n")
    target.chmod(0o600)
print("Restricted relay public key authorized; existing login keys preserved")
