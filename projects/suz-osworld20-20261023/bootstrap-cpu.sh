#!/usr/bin/env bash
set -euo pipefail
umask 077
cd /data/share/lizh639/suz-osworld20-20261023
export CUDA_VISIBLE_DEVICES=''
export NVIDIA_VISIBLE_DEVICES=void
export PIP_CACHE_DIR="$PWD/cache/pip"
export HF_HOME="$PWD/cache/huggingface"
export TMPDIR="$PWD/tmp"
mkdir -p cache/pip cache/huggingface tmp vm logs
python3 -m venv --without-pip .venv
if ! .venv/bin/python -m pip --version >/dev/null 2>&1; then
  curl --fail --location --retry 3 --connect-timeout 20 --max-time 120 https://bootstrap.pypa.io/get-pip.py -o tmp/get-pip.py
  .venv/bin/python tmp/get-pip.py
fi
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install 'torch==2.5.1+cpu' 'torchvision==0.20.1+cpu' --index-url https://download.pytorch.org/whl/cpu
# Install the official environment's dependencies, retaining CPU-only torch.
grep -v -E '^(pynput|ag2|dashscope|google-genai|google-generativeai|wandb|groq|azure-|alibabacloud_|volcengine-|daytona|ui-tars|parallel-web|mcp|transformers|accelerate|anthropic)' OSWorld/requirements.txt > requirements-cpu.txt
.venv/bin/python -m pip install -r requirements-cpu.txt
.venv/bin/python -m pip install nodejs-wheel
.venv/bin/python -c 'import torch; assert torch.version.cuda is None; print("CPU_ONLY_TORCH_CONFIRMED")'
PYTHONPATH="$PWD/OSWorld" .venv/bin/python -c 'from desktop_env.desktop_env import DesktopEnv; print("DESKTOP_ENV_IMPORT_OK")'
date -u > logs/bootstrap.ready
