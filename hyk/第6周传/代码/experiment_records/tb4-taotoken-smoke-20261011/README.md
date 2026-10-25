# Single-task chain smoke test — not a benchmark result

- Terminal-Bench 4.0.0 commit `452bf305c6daa62fc59061d22133a7cbc7c1572e`
- Task: `wal-recovery-ordering`; official separate verifier; one trial, zero retries.
- Harbor 0.24.0; DSH 0.2.0-rc.2; KZ 0.2.4 copied without algorithm changes.
- TaoToken Token Plan Messages endpoint: `https://api.taotoken.net/token/v1/messages`.
- Model `deepseek-flash`, thinking off, temperature 0.
- Smoke limits only: shared 40 requests, 80 tools, 30 minutes, 128k context, 8192 output.
- DSH's internal provider identifier remains `deepseek-official`; actual provider is TaoToken, not DeepSeek direct.
- KZ's historical CNY estimate is NOT a measurement or guarantee of Token Plan Credits usage.
- TaoToken says exhausted plan credits can fall back to account balance. Check plan balance before launching.
- New key enters via local getpass → SSH stdin → in-memory process environment → Docker stdin → DSH child environment. No key in files/arguments/job config.
- No cross-task memory; fresh container and DSH home. No automatic retry or full-suite launch.
- Disable the headless session-title LLM: avoid an unrelated, unbudgeted title-generation request.
- Docker Hub transport uses DaoCloud with the same official SHA256. Verifier packages are supplied offline at the exact official pinned versions; all changes are logged in `transport-changes.json`.
- The Docker bridge cannot reach the internet directly. A temporary CONNECT proxy bound to its gateway permits only TaoToken and package hosts; TLS is not terminated or logged. The real API URL remains the Token Plan URL.
- Run with Harbor `--no-delete`: normal Docker Compose down still removes the trial containers, but retains cached images to avoid slow image deletion. This does not reuse a previous task workspace.
