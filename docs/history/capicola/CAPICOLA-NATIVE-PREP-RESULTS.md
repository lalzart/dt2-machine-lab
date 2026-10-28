# Capicola native preparation results

2026-10-08, Digitakt II OS 1.16. The new compiled preparation worker reads immutable signed 16-bit PCM and constructs Capicola banks in two bounded passes. It is integrated into a separate combined emulator build through an explicit service entry. The test harness still supplies memory and schedules that entry: this is not an autonomous firmware sample loader or an installable OS.

## Changes

`machines/capicola/prepare.c` and `prepare.h` implement count, storage bind, write, publication and cancellation. Each step processes at most 256 frames. Twelve-second input capacity is unchanged. The source remains in caller-owned PCM memory; the worker uses an eight-sample ring instead of making a full float input copy. Exact measured storage is required before the write pass. No analysis or allocation occurs in the audio callback.

Beginning or cancelling preparation invalidates the bank generation, stopping attached readers. Incomplete banks remain unpublished; source identity and generation changes fail closed. Input must remain immutable across both passes, and its owner must cancel before replacement/free. These API obligations do not prove that stock firmware already provides the required lifetime.

`machines/plaits-capicola-prep/machine.c` adds the serialized service entry beside the unchanged R1 audio adapter. `lab/plaits.py` exposes it as the optional `capicola-prep` family. The integration runner's `--native-prep` option uploads PCM and controls only, clears the destination arena, then calls compiled preparation. It compares the resulting keys with a host oracle before exercising the actual stock voice hook. The original `capicola` and Plaits families remain separate.

## Numeric correction

The first native preparation comparison found noise extrema two Q24 timestamp units from the host result. Audio remained within tolerance, but timestamp comparison failed. The target compiler's floating divide is approximate. For int16 input, derivative magnitudes are exact multiples of 2^-16, allowing a bounded integer long division with explicit nearest-even mantissa rounding. This makes the tested native keys exact without changing the preserved float analyzer or relaxing tolerances.

Failed reports are retained: target-01 had a runner bytes-versus-floats comparison error; target-02 exposed the real ratio discrepancy. Target-03 passed after correction. The first combined run reached the voice-hook checks, then its runner incorrectly called the new service address in the old baseline image; the baseline now receives only stock PCM setup.

## Verification

- `out/runs/capicola-prep-host-02/report.json`: 70 exact bank comparisons across silence, impulse, sine, two-tone and noise; input lengths 1, 1024 and 576000; strides 1 and 2; short-case budgets 1/32/256. Eight invalid lifecycle/input cases, changed-input comparator and active-reader invalidation pass.
- `out/runs/capicola-prep-target-04/report.json`: ten native SHARC cases pass with exact key values and timestamps. Maximum audio error 1.20e-7, well within the existing 1e-4 maximum / 1e-5 RMS limits. Stride-2 tests place different data in skipped samples. Memory canaries, exact reader repeat, source-token rejection, cancellation and stale-reader silence pass.
- Maximum standalone worker/test-call count: 260370 emulator instructions. This is not physical cycle timing or a real-time guarantee.
- All 59 existing unit tests, focused Ruff and whitespace checks pass.

`out/runs/capicola-native-hook-02/report.json` passes with native-analyzed banks: 100 actual voice-entry blocks, six Plaits models on both lanes, eight audible stock fallback blocks, eleven malformed-handoff cases and deterministic rebuild. All three stretch control cases match host audio with maximum error 2.24e-8. The bank is 117 keys / 1404 bytes for this 8192-frame source. Largest preparation call is 56528 emulator instructions for this fixture, distinct from the denser standalone noise case above. Existing combined MAIN remains byte-identical; test BLOB SHA-256 is `e1ef63afa3ba75688f64739fdf4f4a6d3c3b514c8b6693336adb1f98afbaf958`.

SINE replay passes in `out/runs/20261008T000344Z-test-053cfd0f/manifest.json`. After the frozen-source runs, contract recipe descriptions were corrected to match the executed fixtures and result notes were completed; executable source and tolerances are unchanged.

## Reproduce

```sh
python3 scripts/check-capicola-prep.py out/runs/<unique-host>
python3 scripts/check-capicola-prep-target.py out/runs/<unique-target>
python3 scripts/check-capicola-integration.py out/runs/<unique-hook> --native-prep
./labctl test sine --replay
```

The native runners use the pinned configured DigiKit runtime. Outputs and derived firmware remain ignored and local. Nothing was committed, published or flashed.

## Next integration boundary

Wire a stock background task to begin/step/cancel preparation, obtain firmware-owned bank storage, and pin the selected sample until completion. Prove replacement, reload, allocation failure and publication through that path. Then add the CPU selector, parameter transport and preparation feedback. Current addresses, storage allocation and service scheduling are emulator fixtures; the twelve-second native load, physical timing, final mixer, listening quality and hardware remain unverified.
