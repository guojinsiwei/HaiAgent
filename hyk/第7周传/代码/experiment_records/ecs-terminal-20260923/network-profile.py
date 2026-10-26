import json
import urllib.request
from urllib.parse import urlsplit

for kind, value in urllib.request.getproxies().items():
    if kind == "no":
        continue
    parsed = urlsplit(value)
    print(json.dumps({"kind": kind, "scheme": parsed.scheme, "hostname": parsed.hostname, "port": parsed.port, "has_auth": bool(parsed.username or parsed.password)}))
