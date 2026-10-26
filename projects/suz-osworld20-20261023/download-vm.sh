#!/usr/bin/env bash
set -euo pipefail
umask 077
cd /data/share/lizh639/suz-osworld20-20261023
mkdir -p vm logs
aria2c --continue=true --max-connection-per-server=8 --split=8 --min-split-size=16M --file-allocation=none --max-overall-download-limit=50M --max-tries=4 --retry-wait=5 --connect-timeout=20 --timeout=60 --console-log-level=warn --summary-interval=60 --dir=vm --out=Ubuntu.qcow2.zip https://hf-mirror.com/datasets/xlangai/ubuntu_osworld/resolve/main/Ubuntu.qcow2.zip
python3 - <<'PY'
from pathlib import Path
import zipfile
root=Path('vm').resolve()
with zipfile.ZipFile(root/'Ubuntu.qcow2.zip') as z:
    for item in z.infolist():
        target=(root/item.filename).resolve()
        if not target.is_relative_to(root):
            raise RuntimeError('Unexpected archive path')
    if z.testzip(): raise RuntimeError('Archive failed CRC check')
    z.extractall(root)
print('VM_IMAGE_READY')
PY
date -u > logs/vm.ready
