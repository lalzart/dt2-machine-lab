# Capicola STRETCH multi-source playback R2

2026-10-08. Status: proposed; implementation authorized by the user asking to continue playback after discussing multiple banks. Lane: source-reimplementation. Revision 2.

## Goal and evidence

Support sixteen tracks using sixteen distinct prepared mono sources through existing STRETCH ID 2, within the existing 8 MiB reservation. Working artifact: a uniquely named native report.json with actual renderer-destination PCM and bank lifecycle evidence. EVIDENCE: R1 exercises 32 readers but only one bank. INFERENCE: multiple banks primarily add preparation and memory; hardware headroom remains UNRESOLVED. This is a local target-build experiment, not installable firmware.

## Preserved source and controls

Reuse the exact R1 stretch.c/h and prepare.c/h analyzer, Q24 transport, smoothstep splices, Hermite interpolation, cached key searches, normalization int16/32768, 12-second input bound and 128-second finite-output bound. The original upstream AGPL source, revision, dependencies, license closure and numeric oracle remain in stretch-contract/source-equivalence.json. No new algorithm or superiority claim. Existing TUNE/BARS/PLAY/STRT/LEN/SAMP/LEV mappings and locks remain; live mode/region behavior remains latched at trigger. No new menu, GAP control, stereo analysis, dependency update, commit, publication, firmware packaging or hardware flash.

## Cache equations and limits

Sixteen descriptor entries; one serialized count/write worker; 32 independent readers. Arena [BANK_BASE, STATE_BASE) = 0x6fff00 bytes. Arrays require 12*measured_key_count bytes, arranged values, whole positions, fractions. First-fit aligned allocation over at most sixteen extents; no compaction, render-time allocation, analysis or copies. Total reservation remains 8 MiB. A worst-case bank still fits, but sixteen worst-case banks need more than this budget. Never infer available hardware RAM from the reservation.

Each maintenance block clears reference/pin flags, pins banks used by active readers, resolves all eligible selected sources, then steps one worker by 32 input positions. Deduplicate identical input address/frame count. Admit into an empty entry, otherwise evict the oldest entry that is neither selected nor pinned. Eviction invalidates bank generation before storage reuse. Selection order is deterministic track order. No eviction of selected or playing banks. Memory pressure leaves the source on stock STRETCH; smaller jobs can proceed. Retry a counted job when a fitting extent becomes available without repeating analysis.

Publication requires unblocked source, matching per-entry epoch, completed write pass, valid bank bounds and generation. LP0 mutation invalidates overlapping entries before PCM writes; matching source header unblocks only that source. Unknown/global mutation invalidates all. Unaffected banks continue. Old custom notes are silent after invalidation until another trigger; readiness never takes over an already playing stock note. Readers latch backend at trigger and otherwise use the preserved R1 behavior.

## Experiment and acceptance

Deterministic seed 1; frozen max PCM error 1e-4 and RMS 1e-5. Host cache tests compare sixteen banks to independent preparation, then render and compare independent floating-position readers. Structural tests cover duplicate sharing, capacity pressure, small-job progress, pin-safe eviction, generation rejection, selective invalidation, retry, fragmentation and guard bytes. Native tests use explicit synthetic mono PCM/slot fixtures and adapted captured control wire: sixteen different samples, both native lanes, PLAY/pitch/BARS diversity, continuous updates, same-source sharing, local reload, unsupported/unready/pressure stock fallback, switch-away and repeat builds. Report emulated block instruction counts separately from DSP cycles. Compare preserved R1 BLOB to its recorded hash, stock/Plaits compatibility, source units and SINE regression. Preserve failures and do not regenerate tolerances/hashes.

## State and failures

Initialization empties cache/readers. Reset/Panic stop readers; callback-free descriptor reset needs serialized maintenance. Sample changes resolve cache at the next trigger; machine changes release lane pins. Reload invalidates before memory changes and reprepares; state recall resolves slots and never persists pointers. Nonfinite controls follow R1 rejection. Freeze/capture and disconnect are N/A for immutable sample playback, with firmware reload events covering input replacement. Cache state equivalence: identical admitted keys, epochs, allocations and exact key arrays for the same operation sequence; PCM tolerance as above. Diagnostic counters are not musical state.

## Remaining evidence

Final mix, native position/UI reconciliation, live mode/trim, comprehensive firmware code ownership, physical DDR latency, worst-case timing, listening and installable integration remain independent gates. Multi-bank success applies only when total prepared data fits the budget; it is not a promise that all sixteen 12-second dense sources fit.
