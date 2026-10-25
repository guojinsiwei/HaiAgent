#!/usr/bin/env bash
set -euo pipefail
umask 077
SETUP="$HOME/terminalbench-v14-setup"
cd "$SETUP"
exec 9>bootstrap.lock
flock -n 9 || exit 0
printf '%s\n' '2cf10babba653310606f8b49876cfb679928669e7ddaa1fb41fb00ce73e64f66  uv-x86_64-unknown-linux-gnu.tar.gz' | sha256sum -c -
tar -xzf uv-x86_64-unknown-linux-gnu.tar.gz
export UV_PYTHON_INSTALL_DIR="$SETUP/python"
export UV_HTTP_TIMEOUT=120
export HARBOR_TELEMETRY=0
UV="$SETUP/uv-x86_64-unknown-linux-gnu/uv"
"$UV" python install 3.12
"$UV" venv --python 3.12 "$SETUP/runtime"
"$UV" pip install --python "$SETUP/runtime/bin/python" 'harbor==0.20.0'
"$SETUP/runtime/bin/harbor" --version
printf '\nRUNTIME_READY\n'
