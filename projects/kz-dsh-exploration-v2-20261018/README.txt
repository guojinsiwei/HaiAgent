KZDSH exploration v2 — 2026-10-18

Scope
User requested future work to focus on the DSH migration (KZDSH). Native KZ is
excluded from this release and from the new comparison. Existing TB2 campaigns
and historical results are untouched.

Authorization
Independent budget ceiling: 96 CNY. Current diagnostic comparison uses 6 tasks
x 2 releases = 12 trials, each capped at 4 CNY; controller ceiling is 48 CNY.
Only TaoToken TokenPlan deepseek-flash is allowed. No GPT experiment calls.
Unused authorization does not trigger extra trials or retries automatically.

Frozen comparison
baseline/src: deployed TB2 merged source from 2026-10-17, hash-locked.
candidate/src: same release with 8 exploration-related files changed/added.
The Critic, completion ledger, transport and provider budgets remain the same.
Both arms use identical task inputs, runtime dependencies, model route, prompt
budget, native execution limits and official graders. Rotating paired order;
two solver slots; grading serialized; no cross-task memory or hidden feedback.
Tasks: 61810_util, cs61_fa24_ants, cs61_fa24_scheme, 61810_mmap,
ap1400_2_hw26, cmu15_445_p1.
Selection is a diagnostic pilot using known failure patterns and controls.
It is not a random sample for estimating benchmark-wide improvement.

Algorithm changes
1. Aggregate failed checks at a declared goal + target set + diagnostic family.
   Preserve exact action/dependency identity for caching and duplicate guards.
   Recognize cosmetic pytest wrappers without merging distinct case selections.
2. A validated Monitor stalled review with two recent complete observations can
   start exploration directly. This is a fallible stagnation judgment; successful
   observations are never relabeled as execution failures. Reject missing,
   incomplete, stale and already publicly passing evidence; deduplicate alarms.
3. Measured exploration names a hypothesis, an alternative and a measurement,
   with complementary comparisons of the same scalar JSON output metric.
   Missing, conflicting, mistyped or incomplete results remain unknown.
   Legacy filename/error-string matches remain observation-only, not support.
   Self-authored measurement semantics remain unverified; no task-success claim.
4. Next active probe must reference its preceding episode result and state how
   it informs repair/verify/revise/retest/defer. Actual dispatch and receipt are
   audited separately. Native edits and ordinary observations require no form;
   optional references on repairs are linked to actual returned evidence.
5. A measured boundary probe can reuse command vocabulary. TF-IDF is telemetry;
   unchanged identical failed actions still need a relevant change/new evidence.
6. End an episode at 8 probes OR 16 total native actions OR 2 format rejections,
   followed by 4 recovery steps of cooldown. No injected diagnostic or task kill.
   Timeout/cancel/tool-error outputs never become stable cached failure results.
   An unrelated passing diagnostic cannot close the original failed issue.

Evidence so far (zero model calls during development/acceptance)
- Linux affected suites on actual DSH packages: baseline 111/111, candidate 123/123.
- Eight deterministic policy failure/control cases: baseline 3/8, candidate 8/8.
  These are policy regression cases, not solved benchmark tasks or efficacy proof.
- Broader copied legacy Windows suite: same 25 failing cases in both releases;
  no newly failing case. Includes stale Critic fixtures and symlink permissions.
  Do not present that broad suite as fully passing.
- Offline actual runtime checks run in network=none containers, verifying native
  Bash, original instruction access, hidden-test isolation, settings and receipt
  propagation. Monitor/Critic are disabled only for this shell acceptance fixture;
  algorithm integration suites separately exercise their hooks and shared budget.
- Official grading of six starter snapshots must succeed before ready.json can
  authorize launch. Scoring validation never exposes graders to solving agents.

Metrics
Report paired official full pass (F2P + P2P), mean F2P, valid scoring coverage,
cost/request/tool usage, engineering failures separately. For mechanism analysis:
episodes by trigger, measured supported/refuted/unknown observations, actual
follow-up use, rejection exits and subsequent public checks. A trigger count or
a matching metric alone does not establish usefulness or correctness.

Files and operation
Local source root: projects/kz-dsh-exploration-v2-20261018
Remote root: /mnt/sdb/home/lizh639/kz-dsh-exploration-v2-20261018
prepare_remote.py: zero-key tests + checked archive restoration under new tags.
accept_remote.py: runtime + grading validation, bounded ledger tests and sealing.
runner.py: independent paired controller; --launch requires ready seal + stdin key.
status.py: read-only aggregate and per-task results.
compare-offline.mjs: deterministic baseline/candidate comparison, zero model calls.
ready.json seals code/config; launch-once.marker prevents accidental replay.
Each solver artifact is saved before grading; a grading failure can be regraded
without buying another solver run. One task's failure never cancels other tasks.

Price ceiling
2026-10-18 TaoToken model detail confirms peak input 2 CNY/M, cache 0.04 CNY/M,
output 8 CNY/M. Off-peak prices are lower. The existing peak-price reservation
formula is retained in BOTH arms as a conservative bound, not a Credits invoice.
Source: https://taotoken.net/models?modelId=deepseek-flash

Startup acceptance correction (2026-10-18)
The first launch failed before any provider reservation. Its eight startup jobs,
starter-only grades and logs are preserved under remote startup-failures/attempt1
and excluded from the paired comparison. The independent ledger had zero calls
and zero spend. Two common deployment adapters were corrected for both arms:
- container-run.mjs imports /opt/kz/deadline.mjs at its actual mounted location.
- boot-guard checks KZ_TASK_INSTRUCTION_PATH, matching the original INSTRUCTION.md.
entry_acceptance.py exercises the actual container entrypoint with every runtime
guard enabled in network=none, using a dummy key and a loopback budget service
that denies the first lease. It must reach that denial on both image families
and both arms. The earlier shell test bypassed the wrapper and missed this bug.
accept_remote.py now requires this complete-entry test before sealing a release.
build_controller.py is a historical one-time generator and refuses to overwrite
the reviewed final controller. Graded engineering failures are reported separately
and are excluded from valid paired solve results.
