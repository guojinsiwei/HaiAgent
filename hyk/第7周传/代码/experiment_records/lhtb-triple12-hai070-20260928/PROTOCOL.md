# LHTB HAI 0.7 full rerun: fixed 12 tasks x 3 methods

This is a new frozen experiment. It does not resume, overwrite or pool outcomes
from the HAI 0.4.0/r3/r4 experiment. The public 12-task manifest, benchmark commit,
container image identities, DeepSeek model, temperature, token limits, tool limits,
wall budgets, official verifier and three-way counterbalanced order are retained.

Methods are BestFGS 0.16.1 collaborative graph, HAIAgent 0.7.0 and Raw using the
same HAIAgent runtime with the context/memory component disabled. Every task-method
pair is a new attempt: 12 tasks x 3 methods = 36 official trials, with three
concurrent slots.

HAI 0.7 changes the treatment only as follows: an unknown environment receives one
audited soft repeat before blocking; explained retries are bounded per exact
action/output; non-submitted runs cannot accept an external success record; and
mechanism utilization is summarized from immutable events. Same-conversation
continuation after a binary official rejection remains enabled and shares the
original cumulative budgets.

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
