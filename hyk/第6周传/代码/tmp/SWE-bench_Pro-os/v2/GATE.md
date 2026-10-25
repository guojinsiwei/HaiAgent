# Release gate — SWE-bench Pro V2 (v2.0.0), 2026-09-22

Run on the exact tree published under `v2/tasks/` with Harbor 0.22 on Modal, 50 concurrent, no registry credentials.

| Check | Result |
|---|---|
| Reference patch (`-a oracle`) | **642 / 642** tasks resolved |
| Empty patch (`-a nop`) | **642 / 642** tasks unresolved (0 spurious passes) |
| Images | `ghcr.io/scaleapi/swe-bench_pro-v2`, pulled anonymously; 642 manifests verified, 211 rebuilt images digest-identical to the graded originals |
| Infrastructure retries | oracle 3 trial(s), empty-patch 3 trial(s) hit Modal sandbox errors on the first pass and passed on re-run (no task-level failures) |

## Infrastructure retries (first pass)

Oracle: `instance_internetarchive__openlibrary-03095f2680f7516fca35a58e665bf2a41f006273-v8717e18970bcdc4e0d2cea3b1527752b21e74866` (EnvironmentStartTimeoutError), `instance_internetarchive__openlibrary-c4eebe6677acc4629cb541a98d5e91311444f5d4-v13642507b4fc1f8d234172bf8129942da2c2ca26` (ConflictError), `instance_navidrome__navidrome-8383527aaba1ae8fa9765e995a71a86c129ef626` (EnvironmentStartTimeoutError)

Empty patch: `instance_internetarchive__openlibrary-03095f2680f7516fca35a58e665bf2a41f006273-v8717e18970bcdc4e0d2cea3b1527752b21e74866` (EnvironmentStartTimeoutError), `instance_navidrome__navidrome-8383527aaba1ae8fa9765e995a71a86c129ef626` (EnvironmentStartTimeoutError), `instance_qutebrowser__qutebrowser-0fc6d1109d041c69a68a896db87cf1b8c194cef7-v2ef375ac784985212b1805e1d0431dc8f1b3c171` (ConflictError)

All re-runs completed with the expected reward. Known timing-sensitive test: `ansible 40ade1f8` (revised test patch) passed on this run.
