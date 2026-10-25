Official DeepSeek Harness vs historical DH: LongCLIBench 20 tasks

Only DSH is newly run. DH reuses the frozen longcli-dh-raw-full20-20261004 arm.
This is a historical practical comparison, not a simultaneous randomized ablation.
Official runtime: @deepseek-ai/dsh@0.2.0-rc.2, headless standard profile.
Source/reference clone under upstream is NOT the executed npm release.
The full npm dependency lock and package-integrity records are retained on the server.

Every task has a new Docker container, writable layer, workspace, DSH home/session
and private internal network. Only immutable runtime and task images are shared.
No previous task's conversation, memory, generated files, or shell state is reused.
Source/logs are saved before destroying the solver container. Official grading uses
another new container, which is also destroyed after reports are saved.

DeepSeek Flash; thinking disabled; temperature 0.
800 total model streams/API attempts, including native title, compaction, retries
and subagents. 600 native root tool dispatches. 7200 seconds per solving task.
Start at one pilot, then at most 4 concurrent solvers and 1 official grader.
No automatic task retry, regrade, budget increase, or completed-job restart.
Provider/authentication or confirmed engineering failures stop new admissions;
already-running work is retained, never discarded or reported as successful.

Default configured context: 16384 tokens with native DSH compaction.
This approximates, but is NOT exactly equal to, historical DH's 48000 characters;
native tool schemas also occupy context. Use Start-DSH20.ps1 -LargeContext only if
explicitly choosing the official million-token window, and label this difference.
Execution platform differs: academy Docker for DSH, CubeStudio exported-toolchain
chroots for historical DH. Task/image versions and official grading are identical.
DSH native file/planning/subagent tools differ in granularity from DH shell calls;
report shell, file/environment and bookkeeping counts separately.

Start locally:
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\54177\Documents\ChatGPT\mcts\experiment_records\longcli-dsh20-20261005\Start-DSH20.ps1"

The entry reruns keyless acceptance, then asks for a hidden fresh API key.
The key travels over SSH stdin, briefly enters a private 0600 tmpfs file, and is
unlinked as the controller consumes it. It is never exposed inside task containers.
Only scoped relay tokens, revoked on task end, enter the task processes.
No key is printed, passed in command arguments, or included in returned artifacts.

Generation/grading continue on the server if the local window closes.
The model-free local relay downloads public logs/reports when finished or paused.
It never calls GPT or any model API; no scheduled Codex monitoring is created.
Return artifacts exclude DSH homes, credential files and raw API payload directories.
Original raw provider requests/responses stay available for a scoped server audit.

Server directory: /var/tmp/lizh639-longcli-dsh20-20261005
Public progress: health.json, summary.json, jobs/dsh--TASK/summary.json, grades/*/result.json.
Remote failures cannot be interpreted as task completion; inspect these records.
