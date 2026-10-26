BestFGS contrastive exploration comparison, 2026-10-01

Isolated common base copied from memory-injection-v8. Original v8, HAI,
production experiments and desktop source bundles are not changed.

Flags: LeanConfig(contrastive_mode='evidence' | 'orthogonal' | 'off').
Off is the default. HAI route_search/stagnation_control are forbidden in both arms.

A / evidence:
- On repeated failure, generate TWO candidate explanations/actions in one model
  reply; execute ONE selected action. Subsequent replies provide one candidate.
- Compare relevant changed variables or discriminating observations, not command
  surface novelty. Same failed executable requires a recorded related file
  change, or one explicitly unverified external-state recheck.
- Condition hashes and cited evidence are checked; semantic claims are NOT proved.
- Preregister literal support/refutation markers, record outcomes conservatively.

B / orthogonal (user proposal):
- Require three nonempty claimed differences: dependency, target, command type.
- Compare command words to latest up to THREE failed attempt records using
  default sklearn-style TF-IDF cosine (lowercase, 2+ word chars, smoothed IDF, L2).
- Use strict similarity >0.8 rejection, matching supplied pseudocode rather
  than the 0.85 mentioned in prose. No relevant-condition retry exemption.
- Stdlib numeric implementation, no new sklearn installation required.
- Empty vocabulary is explicit uncertainty, not a fictitious format violation.
- Dimension declarations are checked for structure, NOT certified as true.
  Strategy prose is NOT included in similarity, matching supplied pseudocode.
- Existing safe argv protocol retained; final_command must represent that action.

Common protocol:
- Same v8 memory generation/retrieval/review, same bounded attempt-memory store.
- Trigger after TWO identical observed failed commands; up to 8 executed tools
  per episode. End after original check completes cleanly or episode tool cap.
- Each rejection consumes a model request. Existing three-consecutive-error
  ceiling prevents unbounded local rejection loops. No free extra model budget.
- No separate judge, trained contrastive representation/loss, HAI routes, graph
  search, alternative execution, branch restoration or macro library.
- Only task-authorized operations; public immutable tool dependency manifests
  are supplied identically to both arms. Dynamic/external conditions unknown.

Experiments:
1. run_policy_comparison.py: six deterministic gate-only probes; no model/CLI.
2. Linux regression tests: actual bounded CLI with mocked model, separately labeled.
3. run_contrastive.py: four paired LIVE provider cases: missing file, numeric
   parameter, local dependency, dimension mismatch; one run/case/arm.
   Same deepseek-flash, thinking=false, temperature=0, output cap 4096 tokens.
   16 logical requests (includes 2 controlled failure seeds), 12 tools, 240 seconds
   per run. Counterbalanced arm order. <=112 provider decisions/224 wire attempts.
   Post-run immutable checker grades separately; cannot guide the actor.
   Record independently correct artifact, submission, actor verification, tools,
   actual API requests/tokens, rejection reasons and raw redacted prompt traces.

This is a diagnostic pilot, not a LongCLI/LHTB benchmark or an estimate of
general algorithm superiority. The latest original experiment remains untouched.
