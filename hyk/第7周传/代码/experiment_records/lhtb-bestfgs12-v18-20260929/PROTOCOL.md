# LHTB BestFGS 0.18 exploratory run: fixed 12 tasks, BestFGS only

This is a new frozen exploratory experiment. It does not resume, overwrite or pool
outcomes from any prior experiment. The public 12-task manifest, benchmark commit,
container image identities, DeepSeek model, temperature, token limits, tool limits,
wall budgets and official verifier are retained.

Only BestFGS 0.18.0 is run: 12 tasks = 12 official trials, with three concurrent
slots. This run is for approximate behavior and failure inspection; it is not a
within-run paired comparison and must not be reported as a confirmatory ablation.
The fixed task identities and official per-task scores may be compared cautiously
with the independently completed HAI run because the benchmark, images, model and
budgets are held fixed.

BestFGS 0.18 uses one continuous main-model conversation instead of reconstructing
the context at every graph expansion. A separately instantiated, bounded advisor
may diagnose stalls, but it cannot replace the main actor or directly submit. The
main actor receives an explicit delivery-progress signal, remaining-budget pressure
and action-conditioned task memory. Branch checkpoints are real container snapshots;
restores and official-verifier continuations retain the original cumulative budgets.
The action and advisor clients have independent message histories while their API
requests share the same fixed total request ceiling.

The supervisor records structured provider credential/balance codes, persists an
outer deadline in each launch intent, terminates only the owned over-deadline process
group, records an infrastructure outcome without replay, reattaches surviving trial
PIDs after scheduler restart, and stops admission before disk reserve is exhausted.

Success is exclusively the official verifier reward. Model submit, exit zero and
local checks are not success. Missing or infrastructure outcomes stay explicit.
Mechanism utilization is descriptive and is not itself a success metric. The three
primary metrics remain official success rate, policy interaction rounds and the
method-blinded contextual tool-redundancy audit.

No task, method or model attempt is automatically replayed. Source hashes, task
inputs, job configs and this protocol are sealed by `preflight.py` before any paid
model call. Credentials are read from hidden stdin, kept in a mode-0600 tmpfs file,
excluded from child task containers/logs, and removed after terminal completion.
