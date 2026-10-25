#!/usr/bin/env bash
set -euo pipefail
umask 022
export HTTP_PROXY=http://127.0.0.1:28761 HTTPS_PROXY=http://127.0.0.1:28761
export NO_PROXY=localhost,127.0.0.1,::1
mkdir -p /home/ecs-user/terminalbench-paired36-20260923/datasets
exec /home/ecs-user/terminalbench-runtime/venv/bin/harbor datasets download terminal-bench/terminal-bench-2 --output-dir /home/ecs-user/terminalbench-paired36-20260923/datasets
