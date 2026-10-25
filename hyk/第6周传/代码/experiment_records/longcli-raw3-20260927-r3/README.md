# LongCLI Raw3 operational recovery r3

Frozen model, task prompts, tool/output/context limits, three tasks and metric definitions
unchanged. This is not a new trial or a method improvement. No repeat of executed tools.
Old experiment directories, artifacts and audit traces remain untouched.

Scheme starts by replaying 569 recorded response/result exchanges without inference or
tool execution, checks the reconstructed next request and current workspace fingerprint,
then continues with the remaining original budget (600 tools, 800 turns, 7200 seconds
minus all previous active wall time). Replay time and network waits also consume budget.
Original 29 r1 responses + 540 actual r2 responses are counted once, not twice.
The first r3 request must pass exact context comparison except wall/budget fields and
host workspace path normalization. Offline replay validation makes zero model calls.

Networking: child-process absolute deadline; validated HTTPS with original hostname/SNI;
DNS cache fresh for 300 seconds and stale fallback only after DNS error within 1800
seconds; try all resolved addresses with bounded connect times. Errors log only stage,
exception type and errno, not keys or provider error bodies. A failed connection expires
the cache so a later attempt resolves again. Eight additional cycles maximum per failing
request, 900-second episode limit, all within original task wall time. Successful requests
reset episode bounds. No cumulative six-recovery-per-task cutoff. No extra auth/certificate
or model-format retries. Ambiguous POST failures can incur provider cost even without a
usable response; attempt logs must remain part of cost reporting.

tmux and 15-second scheduler heartbeat operate remotely without the desktop. A separate
guard restarts orchestration at most three times; independent trial processes are adopted
using PID/start identity. Exclusive intents ensure a launched trial is never started twice.
Uncertain/missing trial processes stop for inspection; they are not automatically replayed.
Network retries
occur inside the current decision with unchanged messages and workspace. A sustained outage
beyond the bounded policy, node reboot/OOM or unsafe workspace state still stops for inspection;
no promise of perpetual uptime, no blind model-trial restart, no GPT monitoring automation.
