# Capicola native preparation worker

2026-10-08 revision 1. User authorized continuation of integration. Source-reimplementation lane; preserve the existing capacity core and combined hook.

EVIDENCE: stock SHARC sample records point to packed signed 16-bit PCM. R1 still receives host-analyzed banks. INFERENCE: a resumable native analyzer can remove that dependency without blocking an entire twelve-second analysis in an audio callback. UNRESOLVED: stock worker scheduling, native allocation ownership and CPU controls.

## Selected architecture and working artifact

Implement a separate C99 worker over immutable caller-owned mono int16 input with stride 1 or 2 (the prepared duplicated 96 kHz voice source uses stride 2). It reuses the exact extrema equations in capacity.c, processing at most 256 input/tail frames per step. Count pass first; caller then binds exact-sized output arrays; write pass second; publication only on successful completion. No allocation, I/O or analysis in cap_tick. Preserve raw source lifetime until completion/cancel. Caller serializes worker/render and must cancel before freeing or replacing source/bank. This is a worker API and compiled target proof, not yet a stock scheduler hook.

Begin invalidates the bank and all attached readers, increments generation, clears count/frames and uses CAP_INPUT_ERROR while unpublished. Source token and generation guard every step. Cancellation invalidates again and clears input pointer. Invalid arguments, insufficient capacity or lifecycle violations fail closed. Frame budget 1..256, input 1..576000, capacity 2..576004. Worker holds ring[8], derivative, last extrema and index/count; no full float input copy. Count-pass completion exposes required keys; binding requires at least that many, write completion must have identical count. Source content must remain immutable between passes; token is not a memory checksum.

Equations: identical capacity.c analyze loop including four zero tail frames, Q24 crossing timestamps, threshold 0.001 and spline interpolation. Quantization is signed16 /32768; stride only selects frames. Reader controls and gains unchanged. State equivalence: exact host keys versus existing cap_load on normalized PCM, exact key count/timestamps and max1e-4 RMS1e-5 target audio; original target-analyzer discrepancy must be reported if reproduced, never masked.

## Experiment and acceptance

Seed1 fixtures: silence, impulse, 220 Hz sine, 220/331 Hz two-tone, deterministic noise; short and twelve-second host inputs. Test budgets1,32,256 and stride1/2 against whole-buffer analyzer, exact host bytes. Verify budget cap, invalid duration/stride, generation/source change mid-load, cancellation, insufficient storage, incomplete-bank silence and successful reader start. Native SHARC build/run uses the same worker on short PCM and compares against host keys/audio, retains any failing fixture. Falsifying comparator: changed input or wrong stride must change nontrivial keys. Store report/builds under out/runs/<unique>. Run existing unit suite and SINE replay. Native source loading, full combined audible frame, CPU menu, bank allocator, installable OS and hardware are deferred rather than inferred from worker success.

## Combined hook continuation

Expose the validated worker as a separate `capicola-prep` build family, including the unchanged R1 adapter. A serialized service entry in the test image manages begin/count/bind/write/cancel at worker state 0x200e4400, updates the existing handoff only on ready, and never runs from the audio callback. The emulator caller provides source address/frames/stride and exact-sized arena storage; it does not upload analyzed keys. Test with the existing 8192-frame combined voice-hook fixture and unchanged R1/Plaits/stock comparisons. The service entry is manually scheduled by the test harness, not attached to a stock firmware worker. All addresses remain emulator-only. This extension is covered by the user's continuation authorization.

For int16 input, derivative magnitudes are exact multiples of 2^-16. The target compiler's approximate divide can shift extrema by two Q24 units. The native worker instead computes that ratio by integer long division, rounding its 24-bit float mantissa nearest-even; it preserves the host equations and original core unchanged. Test this target-specific path against the host analyzer before integration; do not relax timestamp or audio tolerances.
