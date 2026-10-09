# Capicola split-time target experiment

Revision 1, 2026-10-07. User authorization: “Okay let’s continue”, following the precision-blocker report. Continues CAPICOLA-PROTOTYPE.md without modifying its double core or original-header oracle.

Working artifact: standalone compiled SHARC reader output compared with the preserved double oracle, at max error 1e-4 and RMS 1e-5. Host split implementation must meet the same limits first. No firmware voice hook, device upload, quality verdict or publication.

## Numeric contract

Represent every timestamp as signed 32-bit whole samples plus unsigned 24-bit fractional samples, normalized to [0,2^24). Controls in [0.5,2] are binary32 and therefore their sample increments are represented exactly as Q24 integers. Add using integer carry; never accumulate floating absolute times. Quantize extrema fractions to nearest Q24 (at most one Q24 unit rounding error allowed for float tie behavior), retain amplitude arithmetic unchanged. Compare times lexicographically. Convert only local integer/fraction differences to float for interpolation. Storage uses parallel value, whole and fraction arrays. All bounded integer products must fit 32 bits; calculate duration ceil(N/advance) using a split 12-bit multiplication and binary search rather than rounded float division. Maximum input 48000 frames, capacity 4096 keyframes, controls, splice/edge policy and failure behavior otherwise unchanged.

Retain original C99 double core as a separate authoritative comparator, with hashes bound in the new contract. Original source license remains AGPL-3.0 and attribution unchanged. Separate split C99 implementation is not bit-exact by definition: Q24 timestamps may differ by at most 2^-24 samples; output errors must satisfy the original target thresholds. Capacity decisions and active duration must match. Never hide failures by updating tolerances.

## Tests and scope

Repeat the 90 accepted-fixture matrix cases and dense-noise overflow; additional decimal controls (1,0.7), (0.7,1), (1.1,0.7), boundary rates next to 0.5/1/2, two independent states, exact split reset/partition, invalid controls/input and buffer sentinels. Every stored time within 2^-24 of baseline, amplitudes exact on host. Quantized-cursor increments and duration must be exact relative to the input binary32 rate; test all 96000 possible output steps for selected decimal rates and random bounded duration cases (seed 1).

On target, load the same analyzed keyframe values and split times into a standalone arena. First test target analysis on bounded short input, then render full one-second-source sine cases (pitch/advance 1/0.7,0.7/1,1.1/0.7) and short 4096-output-frame impulse/two-tone/drum comparisons. Compare output to double reference, require finite bounded samples, exact repeat, unchanged keyframe buffers and measured per-block instruction counts. If compiler/interpreter faults occur, retain the failure and diagnose without silently editing pinned dependencies. Target host wall time is not hardware DSP load.

One extreme short-leash pitch-quality gap from the first prototype remains outside this numeric experiment. A source-equivalence pass does not resolve listening, stereo, long-sample cache, sample ownership or physical scheduling. Inputs, compiled artifacts, captures, traces and reports go in unique ignored out/runs directories.
