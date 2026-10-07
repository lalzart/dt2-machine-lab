# Flex Lite: remembered-track sampling UI

2026-10-06. Authorized implementation contract; results pending.

The approved gesture is **SAMPLING -> YES record -> YES stop -> YES use**.
The destination is retained across recordings. A new take remains a candidate
until USE; discarding it keeps the assigned take, sequence and track controls.
The normal SRC page plays the accepted temporary sample. No naming or +Drive
sample write occurs in this flow. This extends the passing
[RAM playback prototype](FLEX-LITE-RESULTS.md).

## Implementation boundary

Implement a lab-owned adapter around the pinned OS 1.16 GUI worker, without
editing dependencies. Execute the original recorder page, panel dispatch,
trimming, chunk-request wrapper, sample allocator, channel packing and track
refresh. Intercept the save action before naming and service it at a paused
worker boundary. Restore the interrupted CPU context after bounded calls.

The emulator has no completed DSPI1 recording peer. Supply an explicit WAV
input model: capture advances on the emulated clock; original chunk requests
read its immutable completed take. This is simulated external audio, not a
microphone, physical input, complete DSPI1 electrical model or resampling.
Initial limits: 48 kHz, signed 16-bit mono/stereo, at most 10 seconds. Empty or
too-short takes are rejected without changing the assigned sample.

USE allocates and publishes a fresh slot before changing the target. On error,
keep the old assignment and candidate. Retain replaced allocations for this
bounded session so shared or queued readers cannot see recycled PCM. Reject
the operation when resource capacity is unavailable. Track parameters and
pattern data are not rewritten. TEMP names are session-only; persistence is
outside this adapter and must not serialize these identities.

## Acceptance

- Pin original MAIN, stock GUI snapshot, card, baseline sample feed, native
  runtime and dependency identities; guard hook and string sites.
- Deliver actual panel presses through the existing input queue. Retain OLED
  screenshots, action/state traces and real CPU-generated control frames.
- Record A, accept A, return, record B, discard B, return, record C, accept C.
  Check destination retention, exact trimmed chunk PCM, old-sample preservation,
  unchanged non-slot track bytes, source closure and no sample-storage writes.
- Verify mono/stereo and a destination other than track 1. Check candidate
  failure and resource exhaustion in source tests; reject unsupported input.
- Run original SHARC playback on accepted pages and actual pad-trigger frames,
  retaining exact repeat and stock regression checks. Report voice buffers
  separately from final output and physical timing.
- Include a disabled USE-hook control showing that stock YES still enters
  its save flow. The observed first stage is PLEASE WAIT; reaching that stage
  does not prove naming or completed saving. Do not relabel modeled input as
  physical capture.
- Provide a bounded interactive launcher with the real panel, WAV selection,
  visible remembered target/TEMP state and buffered audition.

Optional Save Sample/Save Project, power-loss recovery, device firmware,
simultaneous capture/playback timing and live audio remain later integration.
No commit, publication or hardware access is authorized by this experiment.
