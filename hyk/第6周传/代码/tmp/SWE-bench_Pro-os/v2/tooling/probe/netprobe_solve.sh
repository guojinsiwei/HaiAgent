#!/bin/bash
echo "=== NETWORK PROBE (agent phase) ==="
[ -z "$LLM_ENDPOINT" ] && echo "LLM_ENDPOINT unset: skipping the model-endpoint check"
for u in https://api.github.com https://raw.githubusercontent.com/NodeBB/NodeBB/master/README.md https://proxy.golang.org https://pypi.org/simple/ https://registry.npmjs.org https://www.google.com "${LLM_ENDPOINT:+$LLM_ENDPOINT/v1/models}"; do
  code=$(curl -s -o /dev/null -m 8 -w '%{http_code}' "$u" 2>/dev/null); rc=$?
  echo "NET $u http=$code curl_rc=$rc"
done
echo "DNS github.com: $(getent hosts github.com 2>/dev/null | head -1 || echo none)"
echo "=== applying gold patch ==="
cd /app 2>/dev/null || cd /testbed; git apply /solution/gold_patch.diff && echo GOLD_APPLIED
