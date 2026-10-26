# SUZ deployment constraints

- The user explicitly forbids use of server GPUs (2026-10-23, supervisor restriction).
- Use external multimodal inference APIs. Do not deploy local GPU models, allocate GPU devices, or start containers with GPU access.
- Experiment hosts may run CPU-only desktop virtual machines, scheduling, logging and official evaluation.
- No GPU rental or alternative GPU server provisioning is authorized.
- Preserve other users' containers and all historical experiment results.
