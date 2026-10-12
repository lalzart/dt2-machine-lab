# Capicola finite-sample prototype

Revision 1, 2026-10-07. Authorized by the user's follow-up: “Alright let’s look into implementing an improved time stretch with Capicola”. The prior feasibility proposal is in CAPICOLA-STRETCH-RESEARCH-2026-10-07.md. This scopes the first local implementation; it does not authorize installation or publication.

Working artifact: a bounded mono offline renderer with a C99 core matching a C++ reference that uses the original Capicola Analyzer and SparseLine. Then attempt standalone SHARC compilation/execution. No machine menu, sample-loader patch, firmware container, stock STRETCH replacement, or hardware operation in this slice.

## Source and adaptations

Capicola 120b0b843c18bda373d96eb79d49805545f61556, AGPL-3.0, Matthew Nielsen / Heavylight Industries. Preserve source notices and record hashes. Port the B-spline extrema analyzer and two-endpoint Hermite reconstruction faithfully. Adapt Granule's separate ideal/audio cursors, keyframe leash, content-adaptive splice length and smoothstep crossfade to a finite sample.

The oracle's analyzer and interpolation are upstream code; its finite transport is new lab code. We claim equality to this explicit adaptation, not to the unmodified live module or the Reddit port. No full module dependencies, detector, distortion, feedback or CV UI.

## Frozen finite policy

48 kHz mono, input 1..48000 normalized finite frames, fixed capacity 4096 keyframes. Analyze the input plus three zero frames to flush the B-spline, then force one terminal frame with a fourth zero. Refuse overflow before writing; never discard keyframes or silently change threshold. Threshold 0.001. Retain float amplitude and double timestamps for the host baseline; 32-bit bounded indices replace monotonic 64-bit ring lifetime counters because the sample cannot exceed one second. Storage uses separate value/time arrays; keyframe equality excludes padding.

Pitch and source advance each range 0.5..2.0, configured at start; leash 16..128 keyframes, default 128. Output duration is ceil(input_frames / source_advance). Source time starts at zero; audio lookup is zero outside [0,input_frames). No implicit looping. Reset/retrigger starts at zero with the same immutable sample. Stop makes further output zero without advancing. Invalid load clears state and reports an error; a valid load is required to recover. Invalid start stops the voice and reports an error. No NaN/Inf or out-of-range input/controls are accepted. Processing after an error remains silent.

The ideal cursor advances by source_advance, actual cursor by pitch. When keyframe-index separation exceeds leash and no splice is active, spawn the incoming cursor at ideal. Fade duration is the source-time span of leash keyframes in the direction of the offset, clamped to at least 48 samples and at most 960; crossfade phase advances pitch/duration. Use the exact upstream smoothstep w=p*p*(3-2*p) and mix incoming*w+outgoing*(1-w). Complete the active splice before starting another. Remove live-writer front/back rescue jumps: a finite file has no moving writer. At the finite duration, stop; multiply first/last 48 output frames by a linear edge ramp min(1, frame/48, (duration-1-frame)/48), bounded below by zero. Unity pitch and advance takes the same reconstruction path, not a PCM bypass. No normalization, gain boost or random DSP state.

Reference C++ and C99 share the finite policy, but C99 reimplements analysis and interpolation; compare keyframes and output separately. Pin operation order and disable floating-point contraction. API processing is sample-based with block wrappers, so partitions 1,32,64,127 must produce identical output for identical events. Target changes to precision are not preapproved: if double arithmetic fails, report the toolchain gap rather than hiding it with float timestamps.

## Validation contract

Generate one-second silence, impulse at 4800, 220 Hz sine, 220/331 Hz two-tone, seeded xorshift32 noise (seed 1), and decaying drum bursts; exact recipes live in the frozen experiment. Test pitch/source-advance Cartesian product {0.5,1,2}, leash {16,128}. Dense-noise overflow is an expected explicit failure at 4096 frames, not a successful audio case. Compare upstream/C99 analyzer counts, amplitudes and times exactly; host output must be byte-identical with matching arithmetic. Repeat, reset, stop, independent instances, partial block tails, invalid inputs, overflow, and deliberately wrong pitch must be covered. Bound PCM to input maximum plus 1e-6, require silence exactly zero, measure 220 Hz tone output within 2 Hz of 220*pitch after edge/splice exclusion. Freeze target acceptance at max absolute 1e-4 and RMS 1e-5 on short vectors; instruction counts are not physical cycles.

Retain input/output raw PCM, WAVs, keyframe comparisons, numeric metrics and source/build hashes in unique ignored out/runs directories. No subjective improvement claim until matched stock STRETCH and candidate renders are auditioned. Stop at a genuine target-toolchain limitation or failed equivalence without claiming integration. A successful target comparison can inform the next sample-access/one-track implementation.
