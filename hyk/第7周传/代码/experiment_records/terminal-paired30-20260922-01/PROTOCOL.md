# TerminalBench paired-30 protocol

- Dataset: `terminal-bench/terminal-bench-2`
- Selection: fixed random 30-task sample from the 80-task non-frozen development pool
- Seed: `20260922`
- Selection SHA-256: `21f67878b6aae59e76d860121e1027ffc110a1dff3c0d005c81c839b77bca847`
- Arms: current BestFGS v10 (`conditioned` experience) and Raw sequential DeepSeek CLI
- Model/API: `deepseek/deepseek-flash`, official API endpoint
- Shared budgets: 24 action rounds, 80 CLI calls, at most 6 commands per action, no adaptive budget
- Sampling: temperature 0.2, provider-default top-p, high reasoning effort
- Reliability: one official attempt per task and arm, zero whole-task retries
- Scoring: official Harbor/TerminalBench verifier reward
- Execution: Harbor 0.20 cloud environments on Daytona; BestFGS and Raw orchestrated by separate Cube containers; two concurrent trials per arm
- Total: 30 paired tasks, 60 method trials

The task list, order, model, budgets, verifier, and retry policy are identical between arms. Infrastructure errors must be reported separately and must not be silently scored as model failures or automatically rerun outside this protocol.
