# Capicola ten-second capacity results

2026-10-07. **Ten seconds is a practical bounded prototype target.** The new core accepts up to 480,000 mono frames at 48 kHz, including the tested dense-noise fixture that exceeded the old keyframe limit. Output duration can reach 960,000 frames (twenty seconds) at advance 0.5. This is host and standalone SHARC reader evidence; safe firmware allocation and physical real-time operation remain unverified.

The [frozen proposal](CAPICOLA-TEN-SECONDS.md) and [capacity contract](../machines/capicola/capacity-contract/implementation-contract.json) preserve the original double and split implementations. The new [capacity core](../machines/capicola/capacity.c) and [header](../machines/capicola/capacity.h) are separate files, retaining the existing Capicola AGPL attribution.

## What changed

The analyzed sample is now a shared bank, separate from each reader's transport state. A count-only analysis pass determines storage needs; the caller supplies exactly sized arrays, then loads the sample. A reader does not allocate or copy sample data while rendering. Playing the same sample twice shares one bank but uses independent playback cursors and controls.

Each keyframe still occupies 12 bytes: amplitude, whole sample index and Q24 fractional position. At most one keyframe is emitted per analyzer iteration, and there are input-frames + 4 iterations. Therefore 480,004 slots are a conservative upper bound for all normalized finite ten-second inputs. This removes the previous signal-dependent 4,096-slot ceiling without throwing away extrema. A caller can supply less storage, but insufficient capacity returns an explicit error, clears bank readiness and preserves buffer guards.

Bank generation changes invalidate attached readers on replacement, including failed replacements. Readers then output silence without advancing until restarted against a valid bank. Bank changes are serialized control operations; this does not supply a concurrent loader, reference-counting allocator or firmware sample ownership system. The caller must keep the bank and arrays alive for attached readers, and use unchanged input and the same arithmetic backend for measurement and loading.

Duration arithmetic now uses three 8-bit limbs. It covers the full new product domain without requiring target 64-bit integers. The old two-limb helper overflows for the nominal pair rate 2 / count 960,000; the negative test reproduces that helper overflow. This is a bound test, not a claim that the previous binary search necessarily evaluated that pair or produced a wrong ten-second duration.

## Memory measured

These figures are **sample data**, not total process memory. Synthetic fixtures are reproducible and do not represent every musical recording.

| Ten-second mono fixture | Keyframes | Keyframe bytes |
|---|---:|---:|
| Silence | 2 | 24 |
| Late impulse | 4 | 48 |
| 220 Hz sine | 4,403 | 52,836 |
| Two tones | 6,623 | 79,476 |
| Decaying drum-like signal | 1,202 | 14,424 |
| Seed-1 noise | 215,359 | 2,584,308 |
| Conservative structural maximum | 480,004 | 5,760,048 |

The maximum is **5.49 MiB per distinct bank**, rather than per playback voice. Dense signals can take more space than raw float audio; this representation is not guaranteed compression. Temporary ten-second float input adds 1,920,000 bytes (1.83 MiB) during loading and can be released afterwards. Worst-case bank plus that input is 7.32 MiB, excluding allocator and metadata overhead.

Measured reader state is 80 bytes on the host and **76 bytes on SHARC**. Bank metadata is 48 bytes on the host / 32 bytes on SHARC. Additional readers of the same sample do not duplicate its keyframes. Multiple distinct samples still require a shared total memory budget before firmware integration; this experiment does not reserve worst-case banks for every track.

## Verification

Host report: [capicola-capacity-host-final-01](../out/runs/capicola-capacity-host-final-01/report.json).
Target report: [capicola-capacity-target-final-01](../out/runs/capicola-capacity-target-final-01/report.json).

- Thirty full host audio comparisons: six ten-second fixtures × five pitch/advance pairs, including decimal rates and both extremes. Counts and amplitudes match the double reference; timestamp error stays within one Q24 unit. PCM tolerance remains max 1e-4 / RMS 1e-5. Observed maximum host error is 2.38419e-7.
- The reference is a scratch copy of the preserved double core with only its two capacity macros expanded. Both original and adapted hashes are recorded. Existing accepted one-second split-core behavior remains byte-identical in the compatibility cases.
- Ten thousand deterministic duration checks, a deliberately wrong-pitch comparator, input peak/finite checks, exact reset/partition, independent shared readers, replacement invalidation, exact-fit and one-short capacity guards, minimum input, and 480,000/480,001-frame boundary checks.
- Compiled SHARC full ten-second sine source, pitch 0.7 / advance 2: five seconds of continuous target output plus a zero tail, rendered twice. Dense-noise start/end windows exercise a 215,359-keyframe bank. Endpoint windows cover output counters approaching twenty seconds and decimal rates.
- Endpoint windows explicitly start from host-generated reader checkpoints. They test target arithmetic, large indices, interpolation and stopping locally, **not** a continuous twenty-second SHARC history. The dense endpoint fixtures must contain at least 100 non-negligible samples, so silence cannot pass that audio comparison vacuously.
- Target tests also check repeat equality, unchanged bank bytes, output/bank sentinels, 25 duration cases, cursor precision and generation invalidation.

All five final target comparisons pass. Worst target sample error is 2.98023e-7. The twenty-second dense-noise endpoint window contains 3,591 non-negligible output samples. Target code is 11,656 bytes; among 8,022 processing calls, median instruction count is 233,010, p99 437,873 and maximum 444,797. Counts include the standalone wrapper and must not be interpreted as physical cycles.

The configured source/native CPU suite passes **59 tests, no skips**. The [SINE replay regression](../out/runs/20261007T125039Z-test-425667ae/manifest.json) passes exact-repeat/baseline, stock isolation, lifecycle and disabled-hook negative checks. Ready-contract validation and focused lint pass; all five preserved baseline source files and both pinned dependency checkouts remain unchanged.

The target keyframes are analyzed on the host. The earlier small target-analyzer mismatch remains unresolved. Sparse finite transport can also fall silent before its duration counter ends, as the preserved reference does; numerical equivalence does not settle that playback-quality question. The sine decimal endpoint is retained as a stop/cursor check, while dense endpoints supply meaningful audio checks.

The target test reserves a separate external emulator arena beginning at `0x83000000`, rejects stock-loader overlap and checks state layout. That is **not** a firmware allocation or proof that the device has that memory available. Compiler instruction counts include wrapper overhead and are not physical DSP cycle timing or callback utilization. No new firmware image was produced.

## Reproduce

```sh
python3 scripts/check-capicola-capacity.py out/runs/capicola-capacity-host-<unique>
python3 scripts/check-capicola-capacity-target.py out/runs/capicola-capacity-target-<unique>
# Use the Python configured in .local/config.json for the whole suite:
python3 -B -m unittest discover -s tests -v
./labctl test sine --replay
```

The target runner selects the configured Python and checks pinned dependencies/fixtures itself. The reference checkout, compiler and dependencies retain the prior versions. Generated PCM, WAVs, binary artifacts, raw states and reports remain under ignored `out/runs` paths.

Before firmware integration, choose a bounded total bank pool and loading/ownership path, resolve analysis parity and assess memory bandwidth plus stock-STRETCH listening. Stereo, loops/reverse, physical timing and hardware tests remain separate. Changes remain local and uncommitted.
