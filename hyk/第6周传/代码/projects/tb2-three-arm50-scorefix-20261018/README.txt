TB2 three-arm50 scoring infrastructure repair, 2026-10-18

Scope: 22 original arm/task IDs. 21 failed before model execution; these may be
retried once after all affected task types pass real, keyless grading acceptance.
DSH torch-pipeline-parallelism already executed its solver: recover its unchanged
submission from exact read/edit records and regrade only. Never call model again.

Model/runtime archives unchanged from boost6. Original 600 CNY shared ledger and
cumulative 4 CNY per original budget_job retained, including uncertain charges.
Global concurrency 6, maximum 2 per arm. One task failure does not stop the queue.

Changes:
- Prepare full verifier dependency caches before grading. Same official pinned
  requirements and Python versions; validate offline resolution, checksum archive.
- Install uv 0.9.5 locally. Serve its exact installer URL from local bootstrap,
  removing dependence on intermittent astral.sh 502 responses.
- Both pip and uv use local dependencies during grading, including non-uv tasks.
- Official task files, tests and verifier timeouts unchanged.
- Reject missing/empty/malformed reports and contradictory success receipts.
- Save paid solver container filesystem before verifier setup for scoring-only
  recovery. Preserve prior trial logs and results; new receipts live here.

Acceptance: accept_scoring.py runs official tests against empty scripted solvers
and the one historical submission. Empty solver score 0 counts as infrastructure
acceptance only, never as a benchmark pass. All 10 affected task types must pass
engineering acceptance before score_retry.py permits paid launch.

Key transmission uses browser copy -> RSA encryption -> SSH stdin -> process RAM;
no plaintext key is saved or printed. No OpenAI/GPT calls used by this campaign.

Important recovery evidence: the original 362-line DSH pipeline file has a syntax
error from its final recorded edit. Recovery preserves that error. Correctness
grading must judge the original submission; engineering repairs do not fix answers.
