#!/usr/bin/env bash
set -euo pipefail
test "$(id -un)" = ecs-user
cd /home/ecs-user/terminalbench-setup-20260923
test -d tools || python3 -m venv tools
tools/bin/python -m pip install --disable-pip-version-check --index-url https://mirrors.aliyun.com/pypi/simple/ uv
export UV_PYTHON_INSTALL_DIR=/home/ecs-user/terminalbench-runtime/python
export UV_HTTP_TIMEOUT=60
tools/bin/uv python install 3.12
test -d /home/ecs-user/terminalbench-runtime/venv || tools/bin/uv venv --python 3.12 /home/ecs-user/terminalbench-runtime/venv
tools/bin/uv pip install --index-url https://mirrors.aliyun.com/pypi/simple/ --python /home/ecs-user/terminalbench-runtime/venv/bin/python 'harbor==0.20.0'
/home/ecs-user/terminalbench-runtime/venv/bin/python --version
/home/ecs-user/terminalbench-runtime/venv/bin/harbor --version
echo 'RUNTIME_COMPLETE'
