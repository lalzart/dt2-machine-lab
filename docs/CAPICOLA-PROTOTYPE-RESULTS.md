# Capicola finite-sample prototype results

2026-10-07. **Original host-core results; direct double port blocked at numeric ABI.**

The later [split-time continuation](CAPICOLA-SPLIT-TIME-RESULTS.md) preserves this baseline and executes a precision-preserving reader on SHARC. The measurements below remain the original experiment.

The [frozen prototype](CAPICOLA-PROTOTYPE.md) follows the earlier [feasibility research](CAPICOLA-STRETCH-RESEARCH-2026-10-07.md). It is an isolated mono C99 source experiment, not a new Digitakt firmware machine. “Improved” audio quality is still a hypothesis requiring comparison with stock STRETCH.

## What exists

- [C99 core](../machines/capicola/core.c): bounded extrema analysis, fractional keyframe times, Hermite reconstruction, independent pitch/source advance, adaptive crossfades, finite duration, edge ramp, deterministic restart and stop.
- [Reference adapter](../machines/capicola/oracle.cc): uses unchanged upstream Analyzer/SparseLine headers with the same explicit finite-file transport. Equality applies to this adaptation; it does not claim identity with Capicola's full live module.
- [Host comparison](../scripts/check-capicola.py), [numeric target probe](../scripts/probe-capicola-target.py), and [six regression tests](../tests/test_capicola.py).
- [Pinned source/equivalence contract](../machines/capicola/contract/source-equivalence.json), upstream license and attribution.

Limits: one channel; at most one second of input at 48 kHz; 4096 keyframes; no looping or reverse; no live controls or sample-loader integration. Pitch and source advance are 0.5–2.0. Advance 0.5 produces twice the duration. The default leash is 128 keyframes. Host state is 49,232 bytes, including 49,152 bytes of keyframe values/times. That is a host layout measurement, not allocated DTII memory.

## Host evidence

Final comparison: [report](../out/runs/capicola-host-final-01/report.json).

| Check | Observed result |
|---|---|
| Keyframe counts, amplitudes and double times | Exact against upstream analyzer for accepted fixtures |
| Main signal matrix | 90 cases of silence, impulse, sine, two-tone and drum-like input; C99/reference PCM byte-identical |
| Decimal rates | Three additional one-second cases at 0.7/1.1 controls; PCM exact |
| Replay and partition | Exact output with tested partitions 1/32/64/127 |
| State/error behavior | Restart, stop, short input, invalid controls, invalid samples, independent states pass |
| Signal bounds | Finite output, peak bounded by input plus 1e-6, silence and post-duration tail zero |
| Dense noise | Expected explicit capacity error; sample cleared and output silent; no truncation |
| Wrong-pitch comparator | Deliberately wrong setting differs as required |
| Tone frequency | 17 of 18 matrix cases have steady-cycle measurements within 2 Hz of target |
| Extreme pitch measurement | Pitch 0.5, advance 2, leash 16 has no complete unspliced cycle after exclusions; acceptance remains incomplete |

The host command deliberately returns **exit 2 / partial**, although the source-equivalence comparisons pass. The extreme-case gap has not been converted into a pass by widening the tolerance. This means short adaptive grains need a separate whole-signal pitch/quality assessment. The default leash 128 passes all nine measured tone settings. Neither that result nor exact reference equality proves subjective quality.

The first diagnostic run included splice-crossing cycles in a frequency metric and reported 115.44 Hz for an expected 110 Hz case. A trace mask now excludes both splice entry and exit, as the original contract required. A subsequent run exposed the no-steady-cycle case above. Failed reports remain in `capicola-host-01` and `capicola-host-02`; no reference outputs or tolerances were rewritten.

Generated WAVs are retained with the final report. For a simple example, [drum-like input stretched to twice its duration](../out/runs/capicola-host-final-01/case-drums-p1-a0.5-l128.wav) uses pitch 1 and source advance 0.5. These were rendered, not auditioned in this session.

## SHARC result and why it matters

The [standalone compiled probe](../out/runs/capicola-target-final-01/report.json) runs through the pinned DigiKit SHARC interpreter. It reports:

- `sizeof(double) = 4`, even when compiled with `-double-size-64`.
- A cancellation input that should preserve `16777217 - 16777216 = 1` instead produces zero after encoding into that ABI.
- The compiler source independently classifies double as four-byte storage and defines `__DOUBLES_ARE_FLOATS__`.

Compiler SHA-256: `1083454e81aa64ce1eb16a1f560840bc88ad0fd3b4d306a66408a6692774f0be`.
Pinned Selache commit: `2b26d3b75c53063575bc5c820fa0d38879335187`.
The probe passes instruction-width checks and returns normally. This demonstrates the numeric incompatibility of the **pinned compiler**, not an inability of SHARC hardware to implement a suitable position representation. Full Capicola audio was not compiled/executed on SHARC, and no physical timing was measured.

A separate [host narrowing diagnostic](../out/runs/capicola-narrowing-negative-01/report.json) compiles the C core with double replaced by float. It is not SHARC execution. Easy binary-fraction rates look deceptively good (maximum error around 1.77e-5), but decimal increments expose drift:

| Pitch / source advance | Maximum sample error | RMS error |
|---|---:|---:|
| 1 / 0.7 | 0.243338 | 0.0693715 |
| 0.7 / 1 | 0.432483 | 0.0477827 |
| 1.1 / 0.7 | 0.173926 | 0.0405766 |

The unchanged target thresholds are max 1e-4 and RMS 1e-5. Naively narrowing positions is unsuitable even for this short prototype.

## Reproduction

Use the pinned Capicola source at `.local/sources/capicola`, with the exact hashes in the contract. The reference build needs an existing Clang C++17 compiler. No third-party runtime package was installed.

```sh
python3 scripts/check-capicola.py out/runs/capicola-host-<unique>
# Expected current exit 2: equivalence passes, one pitch acceptance gap remains.
python3 scripts/probe-capicola-target.py out/runs/capicola-target-<unique>
# Expected current exit 2: pinned target double ABI blocks a faithful direct port.
python3 -B -m unittest discover -s tests -v
./labctl test sine --replay
```

Use the configured Python from `.local/config.json` for all native CPU tests; system Python may skip Unicorn cases. This session's configured suite passed all **46 tests, no skips**. Source lint passed. The full [SINE replay regression](../out/runs/20261007T115836Z-test-38e8761d/manifest.json) also passed, including exact repeat, stock compatibility and disabled-hook controls.

## Next implementation step

Keep this double-precision core and upstream adapter as the reference. Design a bounded timestamp type with an integer sample index plus fractional phase (or an explicitly tested fixed-point representation), with subtraction performed locally so absolute time does not reduce fractional precision. Verify it against the current oracle at decimal rates, extrema boundaries, retriggers and duration limits before adopting it. Do not change the pinned compiler/dependencies silently or weaken tolerances to accommodate narrowing.

Then compile and compare that reader on SHARC. Only after that should we choose safe memory placement, selected-sample access and a one-track firmware adapter. Stereo-linked splices, long-sample storage, loop/reverse behavior, coexistence with Plaits/Flex, stock-STRETCH A/B listening and hardware deadlines remain separate work.

No existing machine source, firmware package or pinned dependency was changed. No commit, push, upload or hardware action occurred in this implementation session.
