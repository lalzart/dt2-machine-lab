# STRETCH replacement R1: transport and native renderer

Revision 1, 2026-10-08. Status: proposed, authorized for uninterrupted local
implementation by the user's request to proceed and get as much done as
possible. Direction and existing native control evidence are in
[STRETCH replacement](CAPICOLA-STRETCH-REPLACEMENT.md).

Working artifact: an optional OS1.16 DSP build using the original type-2
STRETCH CPU interface, native sample transfers/preparation, and direct
STRETCH-destination signal comparisons. No new CPU machine or control overlay.
EVIDENCE level: host structural/signal and compiled native SHARC execution;
real-time, physical device, listening and installable package are deferred.

Source authority: Matthew Nielsen / Heavylight Industries Capicola revision
120b0b843c18bda373d96eb79d49805545f61556, AGPL-3.0, the existing frozen analyzer,
bank, Q24 positions and resumable preparation. Preserve capacity.c/h,
prepare.c/h, the original double oracle and all previous experimental builds.
Add separate stretch.c/h and an independent floating-position reference model.
This is an intentional finite/looping sample-transport adaptation, not a port
of the source module's transient detector or live circular writer.

## Frozen transport

Mono, 48kHz, at most 576000 input frames. Bank arrays and generation remain
caller-owned and immutable during playback. Separate readers own their cursors.
Use positive pitch 1/32..32, positive advance 1/65536..64, leash 16..128.
Convert pitch/advance to floor(binary32 value * 2^24). Non-finite, invalid
bounds or durations fail before attachment/start; never silently clamp.
One-shot duration is bounded to 6144000 output frames (128 seconds). This is
a transport limit, not a larger input or bank. Looping can run indefinitely
with bounded cursors and counters. The initial experiment uses leash 128.

Receive native integer start/end and PLAY reverse/loop flags. Region is
[start,end), 0 <= start < end <= bank.frames. Forward maps relative position
x to start+x; reverse maps it to end-1-x. Positions retain whole/Q24 fraction.
Looping wraps relative positions modulo region length. Normalize all three
cursors by the same whole-cycle subtraction whenever the ideal cursor wraps,
including when actual/incoming cursor becomes negative relative to ideal.
Sparse-key ranks extend across loop cycles, so a wrap does not hide divergence
between pitch and timing cursors. Binary search stays bounded by key count.

Preserve the sparse Hermite reconstruction and smoothstep outgoing/incoming
splice. Trigger a splice when absolute sparse-rank distance exceeds leash.
The incoming cursor begins at the ideal position; both audio cursors advance
by pitch, while ideal advances by timing. Bound splice length to 48..960 source
frames. Phase increases by pitch/splice_length. For forward one-shots at
start=0/end=frames and old 0.5..2 controls, compare against the old reader.

One-shots retain a 48-output-frame entry/exit ramp. Loops use a 48-output-frame
initial ramp and a 48-source-frame taper at each mapped region edge to avoid
an abrupt reset between unrelated endpoint values. This edge policy is an
intentional adaptation requiring listening later. Update pitch/advance without
retriggering or resetting splice/position state. Recalculate remaining finite
duration from the current Q24 ideal position; a rate change never restarts.
Invalidation clears active playback before any bank dereference.

## Native adapter and scheduling

Use the established eight-MiB reservation, with working state in its reserved
200KiB tail and instruction code in the existing experimental L2 region.
Ownership/DDR latency of instruction code remains unresolved. A single shared
bank is selected from eligible STRETCH tracks. Retain its source while any
STRETCH track references it, avoiding oscillation between distinct samples.
Otherwise admit the lowest-numbered eligible track. Validate the stock slot
table, mono flags, rate, sample-pool containment and 141..576000 frame count.
Other sources and stereo use stock STRETCH. Multiple distinct cached banks
are outside R1; the eight-MiB total is not multiplied by track count.

Run the existing two analysis passes in 32-position slices after stock audio
blocks. LP0 page/header callbacks clear publication and advance the source
epoch before changed PCM can be read. No allocation or analysis in rendering.
Initialize 32 independent playback lanes, covering both native lanes of each
track. Bank generation and publication epoch guard every custom render.

Intercept the selector-2 renderer call setup at 0x1c6aee, preserving its native
R4 voice/R8 destination/R12 frame count and stock resume at 0x1c6af1.
On custom success resume at 0x1c6af8. Keep the existing Plaits generic hook.
Preserve all integer/DAG registers across the custom call with the existing
private stack/scratch pattern. Exact firmware hash and instruction-byte guards
must reject unknown input. Do not change selector-2 parameter setup/remapping.

Read pitch/advance from voice+0x1cc/+0x1c8 and native Q31 start/end from
voice+0x198/+0x1a0; PLAY flags from bytes+0x1bb/+0x1bc. Verify the actual output
destination/frame count before claiming audio. Select stock/custom backend at
a trigger; do not take over an already-playing stock note when preparation
finishes. Custom notes invalidated mid-play become silent until a new trigger,
rather than restarting stock from a stale phase. Region/mode changes require
a subsequent trigger in R1; live pitch/tempo updates preserve playback state.
Sample level, release/envelopes and downstream processing keep native authority.

## Experiment and acceptance

Seed 1. Signals: silence, impulse, sine 220Hz and 331Hz two-tone, deterministic
noise and alternating dense input. Int16 normalize by 32768, then use the
unchanged native preparation. Host control matrix: four PLAY modes; pitch
1/32, 0.5, 1, 2, 32; advance 1/1024, 0.02125, 0.5, 1, 2, 16; three regions.
Compare bounded 1024/2048-frame output to an independent floating-position
model using the same frozen key arrays and quantized rates. Host maximum
absolute error <=1e-4, RMS <=1e-5; target uses the same limits. Retain failures
without refitting alignment or regenerating expected values. A one-frame
shift/wrong-pitch comparator must fail a non-silent fixture.

Also check exact repeat/block partitioning (1/7/32/127), old forward-reader
compatibility, terminal silence and exact duration, repeated loop wraps,
negative relative cursors, extremes, long duration, live rate changes,
generation invalidation, invalid inputs/NaN/Inf, independent readers, array
sentinels and peak safety. Use fractional and small-loop boundary cases.

Native checks: captured LP0 transfers, real stock type-2 setup, preparation
without a trigger, first subsequent trigger, direct destination comparison,
stock fallback while unready/ineligible, no mid-note takeover, invalidation
and reload, independent controls for matching tracks, and bounded all-16-track
sharing. Compare stock and Plaits paths/replies; rebuild old Capicola families
and require their recorded image hashes unchanged. Run source tests, formatting
and SINE replay after the final DSP source freeze.

Retain source/fixture hashes, candidate MAIN/BLOB, control/event fixtures,
destination PCM, metrics and failure reports under unique ignored out/runs
directories. Report retired instructions and host time separately from real
DSP cycle timing. No subjective superiority or all-source sixteen-track
hardware support is implied. Record implementation results in a separate
R1 results file without rewriting this proposal fingerprint.
