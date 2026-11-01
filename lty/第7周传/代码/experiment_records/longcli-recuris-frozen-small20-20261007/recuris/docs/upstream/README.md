# Official source audit

Read-only reference snapshot, retrieved 2026-10-06 from the authors' repository:
https://github.com/Gen-Verse/Recuris/tree/7d3745ab787b1206ccd981cb1511100476097266

The commit was obtained from GitHub's repository HTML `currentOid`; the GitHub
REST API was rate limited and `git ls-remote` could not connect. Each saved file
was then downloaded from the immutable raw commit URL. `manifest.json` records
SHA-256 hashes. These files are Apache-2.0 reference material, not an installed
copy of the upstream package. The accompanying LICENSE and notices are unchanged.
No benchmark task, grader, dataset or experimental outcome was downloaded.

## Terminal implementation observed in this commit

- `adapters/tb21/harbor_terminus.py` subclasses Harbor Terminus2. Its three hooks
  rewrite the model prompt, observe command output, and inspect completion.
- `runtime_bridge.py` seeds W from the public task instruction (one compact item,
  at most 2,000 characters); its active bridge does not use the manager's LLM
  blueprint update method. W is marked done at accepted completion, and otherwise
  unchanged W is replaced in the next prompt by a short unchanged marker.
- `tb21_seed/manifest.yaml`: W max_entries=8, boundary injection on first_turn,
  at most eight procedure cards, TerminalCompletionChecker max_blocks=2.
- The seed has one task-neutral `terminal_closed_loop` E card. It recommends
  inspect, minimally modify, then execute and read task/project-native checks.
- The completion checker is a bounded heuristic: it finds mutation and validation
  command regexes and looks for textual failure. It does not establish hidden
  correctness; after two bounces it stops blocking. The bridge subsequently uses
  the last non-timeout receipt to mark pending W done.
- This main revision also dispatches retrieval events on command observation and
  adds lexical error-triggered E delivery (three deliveries max), and minimizes
  the recurring prefix after a configurable default 150 turns. These are release
  implementation details; a paper-first LongCLI adaptation should document any
  choice not to duplicate them.

## Within-task adaptation observed

`tta/driver.py` runs independent Harbor jobs with n_attempts=1. Each task owns a
copy of the seed package. `bare` carries no memory, `m0` carries fixed memory, and
`tta` adds a procedure card after failure. It stops on success. Meta sees public
instruction, actor trajectory, prior E, and one zero-score bit. It is explicitly
not given the verifier implementation, hidden tests, expected output, or other
tasks' rewards. The diagnosis prompt requests one reusable card of <=200 words;
the released parser does not itself enforce the word count. Numeric/date leak
patterns are logged, not an admission gate. The released TTA path does not use
the cross-task paired held-out gate.

The LongCLI reproduction uses the same information boundary and separate attempts,
but JSON memory, stricter proposal validation and explicit incomplete-run handling
are adaptation choices, not claims that this snapshot ran unchanged.

## Cross-task gates are not identical entry points

`metaagent/gates.py::held_out_paired_gate` bootstraps per-task mean differences,
accepts only when the lower paired interval exceeds zero, and caps regressions.
The separate `metaagent/gate.py` command instead requires source repair, positive
held-out net change, and regression cap; it reports significance separately.
Do not describe either function as the unique acceptance formula for every path.
The complete autonomous campaign driver was not included in this small snapshot.

## LongCLI-Bench output contract checked

Read directly at commit `2015f37b5c458f2562354de6b415e9182c91af64`:

- `terminal_bench/harness/models.py`: `TrialResults.is_resolved` is bool or None;
  default failure_mode is `unset`. Normal successful execution can retain unset.
- `terminal_bench/harness/harness.py`: run aggregate is
  `<output>/<run_id>/results.json`; the per-trial result is the source of truth.
  Single-attempt trial_name is `<task>.1-of-1.<run_id>`.
- `terminal_bench/handlers/trial_handler.py`: trial files are
  `<output>/<run_id>/<task>/<trial_name>/results.json`; the agent receives the
  sibling `agent-logs/` directory. Task instruction is taken from task.yaml.
- `terminal_bench/cli/tb/runs.py`: use `--agent-import-path`, `--model`,
  `--dataset-path`, `--task-id`, `--output-path`, `--run-id`, `--n-attempts 1`,
  `--give-test-output 1`, and `--n-concurrent 1`. The fixed CLI uses split('=')
  for agent kwargs, so values containing an extra '=' must be rejected locally.

Missing results, null success, parse/test failures and unknown execution errors
must not become an official false bit. An agent timeout can still have a valid
subsequent official evaluation; its completed verifier outcome is usable.
