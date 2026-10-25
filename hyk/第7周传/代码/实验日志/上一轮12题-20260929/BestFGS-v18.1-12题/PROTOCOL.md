# LHTB BestFGS 0.18.1 repair run: fixed 12 tasks, BestFGS only

This is a new frozen exploratory experiment. It does not resume, overwrite or pool
outcomes from any prior experiment. The public 12-task manifest, benchmark commit,
container image identities, DeepSeek model, temperature, token limits, tool limits,
wall budgets and official verifier are retained.

Only BestFGS 0.18.1 is run: 12 tasks = 12 official trials, with one concurrent
slot. HAI 0.8.2 is already co-resident on the same 12-vCPU node, so the single slot
prevents CPU, memory and Docker-I/O contention. This run is for approximate behavior
and failure inspection; it is not a within-run paired comparison and must not be
reported as a confirmatory ablation or pooled with the interrupted 0.18.0 run.
The fixed task identities and official per-task scores may be compared cautiously
with the independently completed HAI run because the benchmark, images, model and
budgets are held fixed.

BestFGS 0.18.1 uses one continuous main-model conversation instead of reconstructing
the context at every graph expansion. A separately instantiated, bounded advisor
may diagnose stalls, but it cannot replace the main actor or directly submit. The
main actor receives an explicit delivery-progress signal, remaining-budget pressure
and action-conditioned task memory. Branch checkpoints are real container snapshots;
restores and official-verifier continuations retain the original cumulative budgets.
The action and advisor clients have independent message histories while their API
requests share the same fixed total request ceiling. One logical decision may make
at most two audited wire/API attempts when a provider response is not valid JSON;
the logical round, wall budget and total request accounting are not reset.

An interim verifier that explicitly reports `RewardFileNotFoundError` is interpreted
as a binary rejection and resumes the same trial with the same conversation and
cumulative budgets. No other verifier exception is swallowed. The final verifier is
unchanged: a missing reward remains an explicit infrastructure failure.

The supervisor records structured provider credential/balance codes, persists an
outer deadline in each launch intent, terminates only the owned over-deadline process
group, records an infrastructure outcome without replay, reattaches surviving trial
PIDs after scheduler restart, and stops admission before disk reserve is exhausted.
Method/model failures remain visible scientific outcomes but do not halt unrelated
queued tasks. Credential/balance errors, protocol changes, disk limits and hard
infrastructure failures still block further dispatch.

Success is exclusively the official verifier reward. Model submit, exit zero and
local checks are not success. Missing or infrastructure outcomes stay explicit.
Mechanism utilization is descriptive and is not itself a success metric. The three
primary metrics remain official success rate, policy interaction rounds and the
method-blinded contextual tool-redundancy audit.

No task, method or model attempt is automatically replayed. Source hashes, task
inputs, job configs and this protocol are sealed by `preflight.py` before any paid
model call. Credentials are read from hidden stdin, kept in a mode-0600 tmpfs file,
excluded from child task containers/logs, and removed after terminal completion.
