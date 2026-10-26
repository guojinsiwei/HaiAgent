# BestFGS v14 experimental protocol

v14 is a new copy. v12/v13 outputs remain historical artifacts and must not be
mixed with v14 because the submission and metric protocols changed.

## Shared final submission gate

Every arm first creates a draft. A later, separate submission decision must:

1. start from a non-empty implementation patch;
2. run at least one ordinary read-only review command;
3. run at least one public functional verification command;
4. execute every declared command successfully within the common budget; and
5. leave the workspace and cumulative patch unchanged.

A rejected submission retains the draft and consumes the real decision/tool
budget. Submission is not official benchmark success.

## Fixed 2 x 2 causal arms

| arm | graph search | conditioned task-local experience |
|---|---:|---:|
| `raw` | off | off |
| `memory_only` | off | on |
| `search_only` | on | off |
| `bestfgs` | on | on |

Use the same task IDs, prepared environments, model snapshot, sampling settings,
budgets, submission gate and official grader in every arm. The full paired primary
comparison is `bestfgs` versus `raw`; the other two arms may run on a task subset
fixed before outcomes are observed.

## Endpoints

The primary effectiveness endpoint is official benchmark success. Interaction
rounds, tool calls, model calls/tokens, wall time, and graph diagnostics are
separate efficiency/cost endpoints.

`confirmed_reusable_call_rate` is the number of automatically confirmed calls
whose earlier evidence remained reusable, divided by all actual tool calls. It is
an operational lower bound, not a complete semantic tool-redundancy rate. Always
report `classification_coverage`, `unknown_call_rate`, and
`confirmed_reusable_rate_sensitivity_bounds` beside it. The bounds are a label
sensitivity range, not a confidence interval.

`mechanical_repeat_rate` and `legacy_same_command_repeat_rate` are diagnostics.
Neither may be presented as total wasted work. Use `audit_tool_repetition.py` for
a fixed, uniform contextual sample when a broader semantic-waste claim is needed.

## Search and memory diagnostics

Graph arms record node/edge counts, selected source nodes, source-node switches,
equivalent-node merges, candidate/submission activity, validation attempts and
the edge depth of the selected candidate. Sequential-only arms emit graph-only
fields as unavailable rather than zero. `no_workspace_change_transitions` includes
legitimate read-only review and verification and therefore is not a waste count.
The experience funnel remains descriptive and does not alter online rewards.
