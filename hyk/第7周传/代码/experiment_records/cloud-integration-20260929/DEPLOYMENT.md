# Cloud integration deployment — 2026-09-29

Status: **deployed; both complete test runs finished**. Each run: 6 PASS, 6 FAIL, 0 ERROR; failures are reproducible acceptance findings, not deployment errors. See `REPORT.md`.

- Target: `lizh639@172.16.108.236` (existing HAI and BestFGS experiment host).
- Dedicated remote directory created: `/var/tmp/lizh639-mechanism-integration-20260929`.
- Docker server: 29.3.0; root filesystem had 217 GB available during preflight.
- Local payload: `cloud_suite.py`; newly authored synthetic integration tests, no credentials or experiment outputs included.
- Both existing `Start-LHTB12-HAI082.ps1` and `Start-LHTB12-BestFGSv181.ps1` confirm this target.
- Upload was initially rejected by automatic safety review. The user explicitly approved this payload and destination, after which upload succeeded.
- Initial foreground run was interrupted by an SSH disconnect, and had a test-helper error (missing `timeout_seconds` in direct executor calls). That helper was corrected without modifying product sources.
- Second run is detached from SSH with persistent output at `launch-r2.log`; launcher PID was 1188932. Never infer liveness from this historical PID without rechecking.
- Ubuntu complete run: `run-20260929-204730-2c274fd0` (199.815 seconds).
- MATPOWER task-image complete run: `run-20260929-205204-1c55c855` (233.209 seconds), output in `launch-matpower.log`; historical PID 1205993.
- Both runs report no cleanup errors; source copies, artifacts and logs remain available. No paid model calls, no frozen-source modifications.

Intended execution uses the existing cloud Python runtime and copied, hash-verified frozen sources. It tests real Docker adapters with scripted policies, no paid model API requests. Containers have no network, no host mounts, one CPU and 1024 MB memory. Only owned test containers/images are removed; frozen experiments and unrelated services remain untouched. Logs and source manifests remain under a new run directory.

Coverage: filesystem snapshots/restoration/delivery, cwd escape refusal, command timeout/recovery, BestFGS plain versus shell-wrapped diagnostic trigger, advisor evidence validation, HAI relative versus container cwd memory visibility, oversized memory visibility, and outcome classification. The outcome classification cases are synthetic host-side checks, not injected infrastructure failures. This is not a Harbor grading run or real-model algorithm evaluation.

To rerun after confirming no existing test process is active:

```sh
/mnt/sdb/home/lizh639/terminalbench-v14-setup/runtime/bin/python -B /var/tmp/lizh639-mechanism-integration-20260929/cloud_suite.py
```

Set `INTEGRATION_IMAGE=zli12321/lhtb-matpower-opf-regression:20260615` to repeat on the cached actual task image. No image is pulled. Optional `INTEGRATION_CASES` is a comma-separated subset of `docker_lifecycle,best_cases,hai_relative_cwd_memory,hai_container_cwd_memory,hai_large_memory,classifier_cases`. Run with `nohup` and a new log filename to tolerate SSH disconnects. Do not launch while another suite run is active.

Exit codes: 0 = acceptance green, 1 = product acceptance failures, 2 = setup/test errors. Known defects must remain FAIL, not be relabelled PASS. Setup errors must be repaired and rerun before interpreting results. Each run gets its own directory; `latest.json` is written only on completion.
