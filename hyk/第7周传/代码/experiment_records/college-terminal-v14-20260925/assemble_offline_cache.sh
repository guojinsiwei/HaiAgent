#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
test -f offline-verifier-assets.tar
rm -rf offline-source
mkdir -p offline-source offline-cache/python/cpython-3.13.9-linux-x86_64-gnu offline-cache/bin
tar -xf offline-verifier-assets.tar -C offline-source
tar -xzf offline-source/cpython-3.13.9-linux-x86_64.tar.gz -C offline-cache/python/cpython-3.13.9-linux-x86_64-gnu --strip-components=1
tar -xzf offline-source/uv-x86_64-unknown-linux-gnu.tar.gz -C offline-source
install -m 755 offline-source/uv-x86_64-unknown-linux-gnu/uv offline-cache/bin/uv
install -m 755 offline-source/uv-x86_64-unknown-linux-gnu/uvx offline-cache/bin/uvx
./runtime/bin/python stage_tasks.py
./runtime/bin/python build_cache.py
cp offline-cache/offline-cache-manifest.json ./offline-cache-manifest.json
echo '{"phase":"cache_assembled"}' > offline-cache-state.json
