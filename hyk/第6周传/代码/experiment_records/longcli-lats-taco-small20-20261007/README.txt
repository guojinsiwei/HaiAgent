LongCLI small-budget baselines, 2026-10-07

SGE is CANCELLED at the user's request: its RL training cannot be reproduced
with a fixed remote deepseek-flash API. No SGE inference substitute is included.

LATS-CLI: independent implementation of the paper's six-operation search:
selection, five-way expansion, LM/self-consistency evaluation, greedy simulation,
backpropagation and failure reflection. Author code and paper are pinned as
references, not presented as an unchanged official LongCLI runner. The CLI
adapter uses reversible filesystem states and model-generated public-only
verification commands. Internal reward is NOT an official benchmark score.
Defaults: n=5, UCT exploration=1, lambda=0.8, 8 rollouts, depth=40. CLI depth
differs from HumanEval's depth8. Candidate sampling stays at temperature0 to
match the experiment. Exact duplicates are counted for self-consistency and
executed once; candidate diversity is audited, not presumed.

TACO-CLI: unmodified pinned AUTHOR compression modules on a common linear CLI
actor, not the full Harbor/Terminus-2 agent. Includes proposal, conservative
filtering, feedback detection, rule repair, uncovered-output rule creation and
global rule cache. A fresh campaign-scoped pool starts from official seeds.
Task order is fixed; TACO is sequential so cross-task learning is reproducible.
Rules, not solutions/trajectories/hidden scores, transfer between tasks.
Optional upstream LLM-compression tier is retained, with all calls charged.

Both: same pinned public LongCLI20 starters/images and final official grader;
deepseek-flash, thinking disabled, temperature0; 48,000 UTF8 message-envelope
bytes; output4096 tokens; 800 logical calls INCLUDING reviewers, summaries,
rule proposals and repairs; at most2 wire attempts per call and1600 total;
600 actual executed commands across ALL branches; 300s command timeout;
AP26/AP35 3h and other tasks2h; no cumulative token cap was historically set.
Solver resources: 2CPU, 8GiB aggregate, 3GiB process address space,128 PIDs;
read-only root, no network, no keys/socket/tests mounted. New container for
each restored branch, fresh task HOME/tmp; shell processes never persist.
Compared with Cube history this adds an8GiB aggregate cap and changes host/
process semantics. Historical DH48k characters is NOT equal to48k bytes.

Only new baseline40 trials are requested. Historical DH/RAW comparisons are
descriptive, not a matched single-factor ablation. No paid historical reruns
are silently added. An optional raw arm on THIS SAME actor exists for a future
proper TACO on/off comparison, but is not admitted by the default protocol.

Before any paid call: source seals, meaningful offline tests, real isolated
branch rollback, original-starter official scoring roundtrip and control-plane
checks must pass. Free-space/total snapshot thresholds are waived by the user;
actual IO failures still stop the batch. Two included canaries per method precede full admission.
First fatal engineering error stops admission and active peers. No automatic
paid retries. Credentials: fresh local hidden input -> encrypted SSH stdin ->
RAM only. Never use other experiments' keys. Launch claim prevents duplicates.

All artifacts stay on /mnt/sdb/home/lizh639/longcli-lats-taco-small20-20261007.
Existing experiments, Docker service and shared data are never modified.
