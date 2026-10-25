# LHTB HAI 0.8.2 exploratory replay: fixed 12 tasks, HAI only

This is a new frozen exploratory experiment. It does not resume, overwrite or pool
outcomes from any prior experiment. The public 12-task manifest, benchmark commit,
container image identities, DeepSeek model, temperature, token limits, tool limits,
wall budgets and official verifier are retained.

Only HAIAgent 0.8.2 (`hai-v8.2`) is run: 12 tasks = 12 official trials, with three concurrent
slots. This run is for approximate behavior and failure inspection; it is not a
paired comparison and must not be reported as an ablation or comparative result.

Relative to the frozen HAI 0.7 run, HAI 0.8.2 adds a semantic task-local memory
closed loop: evidence can update memory, relevant memories are exposed to the next
model decision, and only current failure/constraint memories may intervene before
execution. Legitimate searches of different files, regions, patterns and offsets
remain distinct; full payload/stdin hashes and argv boundaries prevent false
collisions. Finding/procedure/recovery memories and historical or uncertain items
are recall-only. Intervention, recall, semantic direction change and mechanism
utilization are recorded in immutable events. Same-conversation continuation after
a binary official rejection remains enabled and shares the original cumulative
budgets.

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
