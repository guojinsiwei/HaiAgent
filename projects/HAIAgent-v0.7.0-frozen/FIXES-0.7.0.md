# HAIAgent 0.7.0

- Repeated identical output with an unverified environment receives at most one
  recorded soft retry instead of an immediate hard block.
- A concrete `retry_reason` permits at most the configured number of executions
  for the same command/output fingerprint; prose can no longer reset the loop
  detector indefinitely.
- External evaluation import now requires an explicitly submitted immutable
  artifact. A turn-budget or tool-budget run cannot be labelled successful by
  pairing two null artifact identifiers.
- Run summaries include descriptive mechanism utilization: declared/inferred
  strategies and subgoals, switches, memory admission/recall exposure, and repeat
  decisions. These counts are not success judgements.
- Optional benchmark submission feedback can resume the same conversation and
  cumulative budgets after a bounded binary rejection token.
- Strategy and subgoal ledger observations are deep copies, preventing later
  updates from changing earlier diagnostic records.
