# Experiment constraints

- No server GPU use. External multimodal API inference only; CPU-only GUI environment and evaluation.
- Authorized comparison: 20 identical OSWorld-Verified tasks, SUZ versus baseline, one attempt per arm/task.
- Per-arm/task cap: CNY 8 including all auxiliary calls. Independent experiment cap: CNY 320.
- A new attempt cannot reset a task's cumulative budget. Retain unknown-request reservations.
- Do not substitute another model and report it as native OpenCUA. Model identity, prices and API compatibility must be verified before enabling live calls.
- User subsequently explicitly approved GLM-5.3-Flash for both arms and every SUZ auxiliary role. Label the baseline as OpenCUA execution flow + GLM-5.3-Flash, not native OpenCUA model results.
- Do not expose API keys, start GPT automations, modify ongoing experiments, or delete historical results.
