# Capicola split-time results

2026-10-07. **The standalone compiled SHARC reader passes the numerical comparisons.** Splitting timestamps into whole samples and Q24 fractions removes the previous absolute-position drift. Target analysis is still incomplete: a short two-tone fixture exposes small host/SHARC arithmetic differences. This remains an isolated finite mono experiment, not a firmware machine or a demonstrated improvement over stock STRETCH.

The [frozen split-time proposal](../../CAPICOLA-SPLIT-TIME.md) and [ready contract](../../../machines/capicola/split-contract/implementation-contract.json) extend the [original experiment](CAPICOLA-PROTOTYPE-RESULTS.md). The original double C core and upstream-header oracle remain unchanged and hash-checked.

## Implementation

[split.c](../../../machines/capicola/split.c) retains the original finite transport and stores timestamps in separate whole-sample and fractional arrays. Binary32 pitch/source-advance controls from 0.5 through 2 have exact Q24 increments. Integer carry prevents accumulated drift; only local time differences become float during interpolation. Duration uses bounded integer multiplication and binary search, avoiding rounded floating division at stop boundaries.

Limits remain 48,000 mono input frames at 48 kHz and 4,096 keyframes, with explicit rejection on capacity overflow. State uses 49,232 bytes on both tested ABIs. No heap allocation occurs in the core. Reset, stop, splice policy and 48-frame edge ramps retain their prior behavior. This does not add stereo, loops, reverse or longer-sample support.

[split-target.c](../../../machines/capicola/split-target.c) is a standalone test entry, with no voice or loader hook. The private arena holds code, state, stack and test buffers; the runner rejects overlaps with the exact stock OS 1.16 loader. The linked code is 9,502 bytes. Those are experimental reservations, not validated production memory placements.

## Evidence

Host report: [capicola-split-host-final-01](../../../out/runs/capicola-split-host-final-01/report.json).
Target report: [capicola-split-target-final-01](../../../out/runs/capicola-split-target-final-01/report.json).

| Check | Result |
|---|---|
| Host matrix, decimal and adjacent-boundary rates | 125 audio comparisons pass; worst sample error 1.78814e-7 |
| Host analyzer vs preserved double core | Counts/amplitudes exact; timestamp error at most one Q24 unit |
| Duration arithmetic | 3,000 deterministic bounded cases pass, seed 1 |
| Cursor arithmetic | Every step through 96,000 increments checked at rates 0.5, 0.7, 1, 1.1 and 2; exact relative to binary32 controls |
| Host lifecycle | Invalid input/controls, dense overflow, independent states, reset, stop and output guards pass |
| Compiled SHARC reader | Three full-length decimal-rate sine cases and three 4,096-frame transient/two-tone/drum cases pass at unchanged max 1e-4 / RMS 1e-5 limits |
| Reader input | Identical host-analyzed split keyframes injected into target state; this isolates reader behavior |
| Target repeat and storage | Exact repeat; output sentinels and keyframe arrays preserved |
| Target transport/lifecycle | Exact accumulated cursor and duration; invalid controls and stop produce silence without advancing |
| Source/native CPU regression suite | 54 tests pass, no skips |
| Existing SINE replay | Pass: exact repeat/baseline, stock isolation, lifecycle and disabled-hook negative control |

SINE regression: [20261007T121950Z-test-de118cf8](../../../out/runs/20261007T121950Z-test-de118cf8/manifest.json). Ready-contract validation, focused lint and source-freshness checks also pass.

The compiled reader's worst sample error is 2.38419e-7, compared with errors up to 0.432483 in the earlier host-only narrowing diagnostic. This supports the timestamp design for the tested bounds; it does not establish sound quality or physical deadline margin. Generated target WAVs are retained beside the report and were not auditioned.

The runner measured 6,184 processing calls (normally 64 frames): median 167,064 instructions, p99 233,509, maximum 238,163, including wrapper overhead. This is an unoptimized prototype with repeated keyframe searches. These interpreter instruction counts are not DSP cycles or a real-time utilization estimate.

## Target analyzer gap

The target analyzer runs on four short fixtures. Silence, sine and drum-like input match the host exactly. The two-tone fixture has the same 32 keyframes, but one amplitude differs by 7.45058e-9 and some times differ by up to two Q24 units (1.19209e-7 samples). The exact comparison remains failed, and the target command returns **exit 2 / partial** even when every reader case passes.

The emitted division code uses a reciprocal approximation followed by refinement; floating division near an extrema boundary is a plausible source of these differences, not yet a proven complete diagnosis. No compiler, interpreter or pinned dependency was patched. The raw host/target states are preserved. Before moving analysis onto the device, resolve its arithmetic contract and test the resulting reader output end to end.

Earlier diagnostic run `capicola-split-target-02` trapped because a test-harness edit removed RFRAME; that edit was corrected, restoring the established compiler epilogue handling. Run `-03` stopped at the two-tone analyzer mismatch. Run `-04` retained that mismatch and proved the reader separately. These are retained failures, not replaced expectations.

## Reproduce

Use the pinned private lab configuration, compiler and source reference already recorded by the original experiment. No dependencies were updated.

```sh
python3 scripts/check-capicola-split.py out/runs/capicola-split-host-<unique>
python3 scripts/check-capicola-target.py out/runs/capicola-split-target-<unique>
# Target command currently returns 2: reader passes; target analyzer gap remains.
# Run this with the configured Python from .local/config.json:
python3 -B -m unittest discover -s tests -v
./labctl test sine --replay
```

The target runner selects the configured Python itself and runs `doctor`. It checks state layout, linked instruction extents, output bounds, preserved keyframes, exact repeat, duration/cursor advance, invalid controls and stop behavior. Source hashes and compiler commands are saved with each report. The standalone assembly uses the existing narrowly scoped integer-add encoding workaround; dependencies remain untouched.

## Remaining integration work

Next resolve target analysis parity, then select a bounded sample-analysis and ownership path for one track. Firmware code/data placement, control transport, Plaits/Flex coexistence and stock parity still need their own checks. The earlier extreme short-leash pitch-measurement gap also remains. Matched stock-STRETCH renders and listening are needed before calling this an improvement; physical timing requires separate device evidence.

No firmware image was produced or sent to hardware. These changes remain local and uncommitted.
