Submission-loop repair v3, 2026-10-02. New candidate copied from engineering v2.
No running RAW process, ended campaign, previous source seal or result is changed.
No paid model calls, credential reuse, automatic replay or GPT monitor is added.

Shared actor-loop fix (identical in evidence and orthogonal arms):
1. Record evaluator rejection as S1/S2/... with actual workspace identity.
2. Block any previously rejected workspace before delivery/verifier calls.
   A new summary, whitespace, recall/consult/checkpoint or recheck alone cannot
   unlock identical files. Restoring an older rejected workspace is blocked too.
3. A revised submission must name the latest rejection, a compact hypothesis,
   correction and 1..3 fresh tool evidence IDs. Each check must occur AFTER the
   rejection and against the CURRENT unchanged workspace, with complete clean
   execution and observed non-listing output. Failed/stale/editing checks fail.
   Hypothesis/correction are decision summaries, NOT proofs or hidden reasoning.
4. When an authoritative PUBLIC artifact contract is supplied, use its content
   states too: editing an unrelated log cannot unlock unchanged deliverables.
   Config: submission_artifact_paths=('workspace/policy.py',
          'output/simulation_results.json','output/JOURNAL.md').
   Harbor adapter kwarg accepts these paths and normalizes /app/ aliases.
   Never substitute model-guessed DeliveryProgress paths for this contract.
   Without explicit contract coverage, the guard reports workspace_only and
   cannot determine whether a changed file affects grading.
5. Three blocked proposals since the last actual submission, OR eight rejected
   submissions in one task, stop as submission_stagnation. Reads do not reset
   that limit; the best currently available files are preserved for final grading.
   These are configurable safety limits, NOT an algorithm-success criterion.
   Fixed caps bound cosmetic/same-direction revisions without pretending that
   file hashes or text similarity can judge semantic progress.

Limits: clean commands and changed bytes do NOT prove a meaningful strategy
change, task success, or better score. Arbitrary scripted output may be untrusted;
the guard is not a semantic oracle. A valid repair may need to rerun outputs and
then a stable check before submission. Deterministic file-artifact evaluation
does not permit unchanged-artifact retries for supposed external changes.
Non-file/live-service tasks need a separate explicitly designed retry policy.
Eight rejections is a conservative configurable ceiling and needs live testing.

Entry: sources/bestfgs-project/src/bestfgs/lean_runtime.py
Mechanism: sources/bestfgs-project/src/bestfgs/submission_guard.py
Offline tests: tests/test_submission_guard.py (13 new cases).
Actual isolated Docker smoke: integration/docker_smoke.py (scripted clients).
Deployment must use a NEW campaign and pass each task's public manifest artifacts
to the adapter. This release does not deploy itself or rerun the finished trials.
Verification: Linux 173/173 passed without skips. Windows 145 passed and 28
Linux-only skipped. Actual isolated Docker repeat and repair flows both passed.
Additional legacy test_lean.py has five pre-existing v8 fixture mismatches also
present in v2; these are explicitly recorded, not included in the passing suite.
