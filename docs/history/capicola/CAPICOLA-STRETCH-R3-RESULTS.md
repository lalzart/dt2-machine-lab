# Capicola live STRETCH controls R3 results

2026-10-08. Local OS1.16 source/emulator continuation of the [frozen R3 proposal](../../CAPICOLA-STRETCH-R3.md). The final source and native emulator checks pass; no hardware or installation claim.

## Behavior

The optional `capicola-stretch-live` build keeps existing STRETCH type 2, CPU parameters and locks. PLAY and STRT/LEN now update playing readers. A new configuration maps the ideal source position into the new region/direction, clamps it to the region, and crossfades for 64 output samples. Rapid edits keep only the latest pending configuration. TUNE/BARS stay continuous. Finite completion clears native voice active, stays silent after further edits, and accepts a later trigger.

R1 reader/analyzer and R2 cache are unchanged. Both reader states share the same immutable prepared bank. There is no render-time allocation, analysis or sample copying. The native completion fixture accelerates advance at the renderer boundary after real trigger/setters; it is a lifecycle check, not a normal-tempo performance test.

## Verification

The [fresh frozen native report](../../../out/runs/capicola-live-frozen-02/source/out/runs/native/report.json) passes with `source_fresh=true`:

- Sixteen distinct 512-frame synthetic mono sources and thirty-two independent reader lanes; exact host/native prepared keys; 21,984 bank bytes after 557 additional preparation blocks.
- Forty-eight PLAY-pair/region cases without retrigger, eight continuous rate-update blocks, and thirty-two blocks of simultaneous edits on all sixteen tracks. Live PCM maximum error 1.38e-7 and worst block RMS 5.70e-8, within unchanged 1e-4/1e-5 limits.
- Native active completion, silent valid edits after completion and trigger restart. Selective LP0 reload, pressure fallback and switch-away still pass.
- Forty-eight stock/Plaits parity blocks and four pressure-fallback PCM comparisons; deterministic candidate bytes and exact preserved R1, R2 and MAIN hashes.
- Sixteen nonzero master/ring output blocks, peak 0.489. Ring conversion with the independently verified native polarity matches at zero LSB error. This checks passage through the modeled output stage; it does not prove the entire effects/mix against an independent oracle.

The [host report](../../../out/runs/capicola-live-frozen-01/source/out/runs/host/report.json) passes 576 independent live-control comparisons: max 1.92e-7, RMS 5.66e-8. Rapid seven/thirty-two-sample edits, exact partitioning, invalid controls, bank retirement and a deliberately latched-control negative comparator pass. The latter differs by 0.977 and falsifies an implementation that ignores live edits. Five focused C-state tests include bit-exact unchanged-control PCM against the preserved C reader.

All 138 source tests pass in [the final snapshot log](../../../out/runs/capicola-live-frozen-02/units.log). The first snapshot's new layout test used the wrong region name; that test typo was fixed without changing DSP code. The [SINE replay](../../../out/runs/capicola-live-frozen-01/source/out/runs/20261008T120501Z-test-f46d833c/manifest.json) passes repeatability, stock isolation, trigger lifecycle and its signal checks. [Source comparison](../../../out/runs/capicola-live-frozen-02/sine-source-comparison.json) confirms unchanged lab/machine executable inputs between the SINE snapshot and final snapshot. Final source is retained with [snapshot hashes](../../../out/runs/capicola-live-frozen-02/snapshot.json) and a [checkout comparison](../../../out/runs/capicola-live-frozen-02/checkout-comparison.json).

Candidate BLOB SHA256: `0cfb6c8315bd2db0e7346527c2834907fa7d131b0b55faf04f047d2ebb801faf`. MAIN SHA256: `7f19553cc4bbdf170378ba67c85bedcf4a57a1d10a4a9751080e249547bd8ff3`. Code 90,244 bytes; constants 12,496 bytes. Dependency revisions and original firmware hashes remain pinned.

## Resources and limits

Thirty-two lanes grow from 4,224 to 8,832 bytes, adding 4.5 KiB inside the existing 200 KiB working region. The sample-pool reservation stays 8 MiB, with 7 MiB minus 256 bytes available to cached banks, and the source ceiling stays twelve seconds. Sixteen distinct prepared samples can play when their banks fit; dense sources can still require stock fallback. See [R2 capacity results](CAPICOLA-STRETCH-R2-RESULTS.md).

Normal playback has one reader per lane. A live transition has two for 64 samples, approximately 1.33 ms at 48 kHz. Continuous edits across all tracks can keep transitions running. The first simultaneous-edit attempt exceeded the four-million-instruction harness cap, retained at `out/runs/capicola-live-frozen-01/native.log`. Only the stress fixture now has an eight-million-instruction cap; this is an emulator execution limit, not a DSP cycle budget. Hardware headroom remains unmeasured.


The same short-source fixture records these retired-instruction counts per 32-output block:

| Condition | Instructions per block |
| --- | --- |
| R2 steady distinct sources | 2,198,973–2,409,631 |
| R3 steady distinct sources | 2,321,917–2,532,575 |
| R3 live changes on track one | 2,436,485–2,906,969 |
| R3 simultaneous rapid edits on sixteen tracks | 2,312,976–4,459,587 |

Steady playback is approximately five to six percent higher in the corresponding fixture ranges. The stress peak is about 1.76 times the R3 steady maximum. These are whole-block emulator counts, not hardware cycles, DSP utilization or a hard upper bound for arbitrary sources. Dense banks, effects and long-duration native playback need separate profiling. Settled playback after the stress fixture returns below 2.19 million instructions per block, with different resulting regions/modes.

## Output audit

`out/runs/capicola-output-audit-01/result-02/output.json` observes nonzero master and DAC-facing ring data for both candidate and stock. The direct positive-Q31 comparison failed because pinned native execution negates both ring channels after conversion. `polarity-02/candidate-before.json` and `stock-before.json` stop at 0x1c758b and confirm the preceding conversion is positive and correct. These current observations differ from the older dependency note describing left-only inversion. The final runner accounts for the verified native polarity with the same one-LSB tolerance; the playback code and pinned dependency were not changed. This establishes a modeled output boundary, not physical DAC polarity, listening quality, or an independent full-mix oracle.

## Remaining integration

Native active completion is integrated. Native phase and elapsed/stretch-progress words still retain stock seed/setter behavior: +0x190 is loop start, +0x1b0 is phase, and +0x1c0 is elapsed output count. Updating these requires a separate semantic/consumer check. Full UI/playhead reconciliation, project lifecycle, permanent L2 code ownership, physical DDR/deadline measurements, stereo and packaging remain open. No commit, device transfer or flash was performed.

## Reproduce

```sh
./labctl doctor
python3 scripts/check-capicola-stretch-live.py out/runs/<unique-host>
python3 scripts/check-capicola-stretch-live-native.py out/runs/<unique-native>
python3 -m unittest discover -s tests -v
./labctl test sine --replay
```

Native checks and source units use the configured Python 3.12 environment. Captured LP0/control inputs stay hash-guarded; synthetic sources are explicit fixtures. Native tests use compiled SHARC in prepared stock-initialized emulator state; MAIN remains exact and the earlier CPU parameter/lock evidence is inherited.
