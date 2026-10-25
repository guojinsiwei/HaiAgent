RE-TRAC LongCLIBench fixed20 — academy Docker, 2026-10-06

Source: Desktop/retrac-handoff.zip, archive SHA256
abce18298d86989975885209621b767da29b416c866e7b3233d687475f31a50e
This is the handed-off independent paper implementation, NOT author-official code.
The full MANIFEST.sha256 is checked; engine.py/client.py/prompts.py are unchanged.

Only RE-TRAC is newly run. Existing DH/RAW/DSH trials are not restarted.
Model: deepseek-flash, thinking disabled, temperature0.
Per task: 800 logical model calls INCLUDING compression/format repairs; max2 HTTP
attempts each, wire ceiling1600; 600 terminal calls; output4096tokens; input48000
UTF8 JSON bytes; observation24000bytes; maxwait300s; AP26/35 wall3h, others2h.
Original8 rollouts x50 action steps, full eight-heading recursive memory.
Last rollout is delivered; no hidden-test feedback, test-based selection or retries.

20 exact pinned tasks/inputs/toolchain base IDs and official grading commit:
2015f37b5c458f2562354de6b415e9182c91af64.
4 simultaneous task containers, 2CPU each, cores16-23; AS3GiB per process.
Original official TmuxSession + RE-TRAC TmuxTerminal; same keystroke/poll/Ctrl-C
contract. Linux prlimit adapts Docker's absence of --ulimit as. Only the public
timestamp helper uses exec-stdin transport to work around Docker tmpfs/RO archive.
Every task has a fresh anonymous app volume, HOME/tmp, terminal and model state.
Rootfs read-only; no capabilities, privilege gain, host credentials, Docker socket,
hidden tests, host PID visibility, or external task networking. Key remains only
in the trusted host client; never in task environment. Final app is copied while
paused, then owned task container/volume removed. Failed trial sources are rescued
before cleanup where possible; a failed rescue keeps the stopped container.

Differences from historical Cube: physical CPU/host, Docker /proc namespace,
native persistent tmux instead of subprocess/PTy adapter, no16GB Cube parent cap.
AS3GiB is a PER-PROCESS limit, NOT a3GiB total-memory container limit.
RE-TRAC has no function tool schema; historical DH counted characters, DSH counts
its native schemas. Matching48kbytes is not matching input tokenization/interfaces.
Native nonblocking duration limits waits, not the lifetime of foreground jobs.
These differences are logged in protocol.json; this is NOT a perfect host ablation.

All grading runs on academy automatically: one final immutable source artifact,
unmodified official grader/tests/parser, 8CPU/8GiB, sequential per campaign.
No model calls are used for grading, scheduling or monitoring. No GPT automations.
Local PC can disconnect after key submission. Public-only manual progress:
ssh -i C:/Users/54177/.ssh/cubestudio_notebook lizh639@172.16.108.236 "/var/tmp/lizh639-longcli-retrac20-college-20261006/runtime/bin/python -B /var/tmp/lizh639-longcli-retrac20-college-20261006/status.py"

Start-Retrac20.ps1: hidden local key input, ready seal verification and new run
claim. NEVER rerun after an uncertain launch; inspect public status first.
Known Cats READMD.md starter P2P defect is retained, not repaired or hidden.
No paid solving is allowed until original tests, adapter tests, all four real
Docker basic/pressure fixtures and official Cats starter grading pass.
