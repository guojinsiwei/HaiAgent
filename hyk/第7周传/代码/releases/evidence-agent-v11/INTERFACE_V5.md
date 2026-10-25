# Shared model interface v5

Both BestFGS and the raw CLI baseline use the same client and unchanged model,
temperature, reasoning effort, task environment, action/tool budgets and metric definitions.
No planner, memory, patch generator, semantic judging or search is added to the raw baseline.

- SSE requires both `[DONE]` and a terminal `finish_reason`. Incomplete/malformed
  streams are transport/interface failures; their partial commands are never run.
- `length` and other non-`stop` endings cannot be accepted even if content parses.
- Empty content, invalid JSON and non-object JSON get identical syntax-only feedback
  within the existing 5-request limit, not an additional retry budget. Existing
  method-specific schema checks retain their 3-attempt limit.
- Failed requests retain received token usage. Requests whose usage cannot be
  obtained (for example a worker killed at the wall deadline) are counted as
  unreported; those costs are unknown, not zero. Provider billing is authoritative.
- Each attempt's snapshots/model-failures.jsonl records failure type, finish reason,
  integrity flags, content length and redacted bounded output (head 6000/tail 2000
  characters). Known keys/bearer tokens are removed; this is not a general PII filter.
  Do not publish raw diagnostic logs without review. Prompts/auth headers are not logged.
- Syntax and schema failures remain distinct from solved/unsolved benchmark outcomes.
  Existing public validation is not official SWE-bench grading.

The v4/v2 pilot was explicitly stopped by the user. Preserve it without overwriting
or pooling results. Restart all 100 frozen IDs, both methods, in a fresh results root
and freeze the new protocol/code hash before launch. Model-output failures that exhaust
the fixed retries are completed attempts; the external guard must not rerun them.

This improves diagnosis and recovery of formatting errors; it does not guarantee
valid model outputs or prove what caused old failures whose raw responses were lost.
