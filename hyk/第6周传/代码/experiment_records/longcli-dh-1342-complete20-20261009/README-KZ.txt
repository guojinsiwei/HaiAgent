KZ = historical DH subgoals + routing 1342, large capacity.

Frozen algorithm: original run /var/tmp/longcli-dh-routing3x7-20261008.
136 solver/runtime/environment files remain identical. No recent DH tools or
new prompts, memory rules, recovery counters or graph search were imported.
Model deepseek-flash, thinking disabled, temperature 0; same official task
commit/images/grader. Four roles share 800 wire attempts and 600 tools per task.
Input 1M tokens, output 32768 per request, actual wall 7200 seconds.

Old seven results remain immutable. Only their complementary thirteen run here.
Aggregate concurrency remains six; original three-arm run had two per arm,
whereas this single-arm supplement admits up to six. This deployment difference
is visible in KZ-config-lock.json, never described as identical scheduling.

New safety policy: CNY50 upper-cost ceiling per task, all four roles/retries.
Official peak prices verified 2026-10-09: hit .04 / miss 2 / output 8 CNY per 1M.
Peak prices form a conservative upper bound, not the account invoice. Holidays,
off-peak prices and discounts can make the actual bill smaller. No usage is
not treated as zero cost; full request capacity remains reserved.

Already-running historical workers: external response watcher active, preserves
final source for official grading at cutoff. An in-flight provider request can
still be billed; this mode cannot guarantee an exact atomic CNY50 invoice cap.
NEW workers through guarded_trial: reserve the worst-case request cost BEFORE
transport. If remaining money cannot cover it, refuse that request, preserve
source, classify cost_budget_cny and continue other tasks. No output/budget or
solver-algorithm changes to fit the money. cap events are cost-censored results.

The historical seven had no cost ceiling. Compare common solver/configuration,
and disclose any binding cap; do not claim all twenty had an identical monetary
budget. A fixed API alias also cannot freeze provider backend/availability.

No key in files, arguments, logs or reused credentials. No GPT automation, no
emails. The server-side cost watcher is deterministic and calls no model API.
