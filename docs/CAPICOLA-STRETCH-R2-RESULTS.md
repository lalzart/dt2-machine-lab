# Capicola STRETCH R2 playback results

2026-10-08. OS1.16 local emulator prototype. Up to **sixteen distinct mono samples** now have independent prepared banks behind the existing STRETCH machine, within the unchanged 8 MiB reservation. Each track has two native reader lanes, thirty-two total. Identical samples share a bank. This remains a capacity-dependent prototype, not hardware-ready firmware.

The [frozen proposal](CAPICOLA-STRETCH-R2.md) and [contract](../machines/capicola/stretch-multi-contract/) preserve the original R1 analyzer, reader, controls and tolerances. R1 is still separately buildable and its BLOB hash remains exact.

## What changed

A sixteen-entry cache uses measured key counts, one serialized count/write worker and first-fit allocation inside the existing 0x6fff00-byte bank arena. All existing selected sources are marked before new admissions. Selected or actively playing banks cannot be evicted. Unreferenced inactive banks may be reclaimed; generation changes prevent old readers from accessing reused arrays. Fragmented memory can cause fallback even when total free bytes look sufficient; there is no compaction in the audio path.

A large bank that cannot fit does not block smaller jobs. Retained counts allow retry when space becomes available. LP0 page/header hooks invalidate affected source epochs before PCM writes; unrelated banks continue playing. Invalidated custom notes remain silent until a new trigger. Unready, unsupported or memory-limited sources use stock STRETCH, with no mid-note takeover. No allocation, preparation or sample copying occurs in the renderer.

## Verified playback

The [final native report](../out/runs/capicola-multi-frozen-01/source/out/runs/native/report.json) passes with a fresh frozen source snapshot:

- Sixteen distinct explicit synthetic 512-frame mono samples, thirty-two native lanes, sixteen distinct PCM outputs, all four PLAY modes and varied native TUNE/BARS.
- Native prepared key values and Q24 timestamps exactly match independent host preparation for all sixteen sources.
- 512 output frames per lane match the independent reader: maximum error 1.357e-7 and worst block RMS 4.407e-8, below frozen 1e-4 / 1e-5 limits.
- Eight continuous-control blocks across all lanes, all-track bank sharing, distinct-source restoration, overlapping page invalidation through original native LP0 routines, matching headers, reload/retrigger and switch-away.
- Four reduced-budget stock-fallback blocks are PCM-identical to the stock reference; forty-eight stock/Plaits enclosing-block comparisons are exact.
- Repeat builds are exact. Original R1 BLOB and CPU STRETCH interface hashes are preserved.

The synthetic sources/slot records and adapted captured wire are explicit fixtures. They do not claim sixteen samples were selected through the physical panel. The output boundary is the actual STRETCH renderer destination before native envelopes/effects and final mix.

## Capacity and processing cost

Short native fixtures require **21,984 bytes** of bank storage. Preparation completes after 557 additional normal audio blocks; these block counts are not physical wall time. Cache metadata occupies 1,436 bytes and the existing reader states are unchanged. Candidate code is 85,008 bytes, constants 12,496 bytes, with working memory in the existing reservation; L2 instruction ownership remains unresolved.

The [long-source host check](../out/runs/capicola-multi-capacity-01/report.json) runs the same frozen cache/analyzer with sixteen 576,000-frame inputs (12 seconds each), guard bytes and the production arena size:

- Sixteen tones at 100, 150, ..., 850 Hz all fit: **2,189,376 bytes (2.09 MiB)**.
- Sixteen independent seeded noise sources fit **two banks**, totaling **6,201,840 bytes (5.91 MiB)**; fourteen remain under pressure. Existing banks and arena guards remain valid.

These are host capacity observations, not native long-source audio or hardware timing. Sample spectra determine key density; the tone result does not promise sixteen arbitrary twelve-second samples will fit. A maximum bank still needs 6,912,048 bytes; sixteen maximum banks exceed this reservation. Source PCM remains in the original sample pool.

In the native short-source fixture, all-track distinct-source playback retires **2,198,973–2,409,631** emulator instructions per 32-frame block. All-track sharing retires **2,152,887–2,258,579**. Different spectra produce different reader work, so this comparison does not isolate cache overhead. It demonstrates similar order of measured workload, not a hardware load percentage or deadline margin. No timing claim follows from emulator instruction counts.

## Checks, corrections and artifacts

Nine focused cache tests cover independent bank/PCM parity, sharing, pressure fairness, pinned retention, retry, selective invalidation, count/write interruption, invalid inputs and fragmentation. The [full source log](../out/runs/capicola-multi-frozen-01/units.log) passes **132 tests**. Ruff check/format, strict relocation/layout guards and bundle readiness pass. The [SINE regression](../out/runs/capicola-multi-frozen-01/source/out/runs/20261008T104814Z-test-26954faf/manifest.json) also passes, including its freshness gate, exact repeat/baseline, lifecycle and stock isolation checks.

The first native run passed sixteen-source playback but failed its synthetic C-callback return harness. It was replaced with the original native page/header routines. The second run failed pressure PCM comparison because only the candidate advanced through waiting blocks; identical reference scheduling fixed the comparison without changing tolerances. A host fragmentation test initially assumed disjoint holes could fit a larger bank; it now verifies pressure until a contiguous extent is released. These failures remain in local runs. The third native run passes but broad source freshness is false because harness/metadata edits continued; the final frozen run is fresh.

Final source is under [snapshot.json](../out/runs/capicola-multi-frozen-01/snapshot.json). The [checkout comparison](../out/runs/capicola-multi-frozen-01/checkout-comparison.json) records that the current Capicola, reader, layout and shared build inputs match the tested copy before results backfill. Unrelated Flex/resource work is preserved.

- BLOB: `2065ca81247367d0e46561e8ae582746b041aeea7a03f9bee0a6fd9021dded01`.
- MAIN: `7f19553cc4bbdf170378ba67c85bedcf4a57a1d10a4a9751080e249547bd8ff3`.

The final native directory retains banks.json, distinct-renderers.f32, synthetic-pcm.s16, exact candidate/repeat images, assembly/listings and memory layout. The long-source directory retains its exact check.py, C helper, source hashes and per-bank capacity report.

## Reproduction and remaining work

Use uniquely named output directories and the configured Python 3.12 runtime:

```sh
python3 scripts/check-capicola-stretch-multi-native.py out/runs/<unique>
python3 -m unittest discover -s tests -v
./labctl test sine --replay
```

Preparation remains serial, bounded to 32 input positions per normal block; preparing sixteen large sources can therefore take substantial scheduled audio time. Mid-note PLAY/trim remains latched until the next trigger. Native position/UI bookkeeping, stereo support, full final-mix checks, comprehensive runtime ownership, physical DDR latency/deadline measurements, listening and installable packaging remain open. No firmware was sent to hardware and no commit or publication was made.
