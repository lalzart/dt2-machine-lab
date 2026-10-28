# Flex Lite: RAM sample playback prototype

2026-10-06. Digitakt II **OS 1.16**. **Passed in prepared emulator execution.**
RAM-backed mono and stereo samples play through the stock ONESHOT renderer,
with output identical to file-backed loading and zero emulated storage
operations during temporary loading, assignment, unloading and replacement.

The prototype supplies synthetic PCM from host RAM to the original sample
loader, selects the allocated slot on a track, and runs the stock ONESHOT
renderer. It exercises the playback half of **record, use immediately, save
later**. Actual recorder input and the panel workflow remain separate work.

Implementation: [RAM adapter](../../../lab/flex_lite.py),
[bounded probe](../../../scripts/probe-flex-lite.py),
[frozen experiment contract](FLEX-LITE-PROTOTYPE.md).

## What runs

`immutable RAM PCM -> stock loader and allocation -> stock page/header packing`

`-> modeled LP0 delivery -> stock SHARC callback -> stock ONESHOT voice output`

The loader uses a session-only identity. Seven host hooks provide reference
resolution, key, open, size, read, name and close operations for that resource.
They are scoped to a dedicated RAM-only loader instance, after loading the
background sample normally; they are not a mixed-source browser integration.
The original CPU code still allocates sample memory, separates stereo
channels, publishes PCM and metadata, and maintains its slot bookkeeping.
This is a host emulator adapter, not an installed firmware feature.

The RAM test drive contains only an unrelated background sample. The target
audio exists in the adapter's RAM. An independent comparator loads identical
audio normally from a separate emulated drive. Both paths begin with the same
stock snapshot and produce the same controlled track assignment.

Track 1 assignment is a deliberate guest-RAM edit followed by original row
refresh and bounded interrupt-handler frame construction. The DSP probe then
sets documented control-frame fields and a trigger explicitly. This verifies
the slot through CPU bookkeeping and frame packing; it does not demonstrate
a panel gesture or normal sequencer playback.

The LP0 adapter stages packets in the DMA receive buffer and executes the
original completion callback. DMA/interrupt entry and resubmission are modeled.
It does not inject the sample pointers into the SHARC voice directly.

## Acceptance evidence

Passing [report](../../../out/runs/flex-lite-06/report.json) and
[artifact audit](../../../out/runs/flex-lite-06/artifact-audit.json).
The run retains source copies, source hashes, native state, CPU-generated
pages, assignment frames and rendered audio under
`out/runs/flex-lite-06/`. The binary fixtures remain ignored and local.

The matrix uses 12,000-frame, 48 kHz int16 sources: mono and distinguishable
stereo channels. Each format covers base playback, +12 semitones, start/end
trim, forward looping, reverse and reverse looping. Every case compares RAM
loading against file loading and an exact repeat, with byte-exact float32
voice PCM as the oracle. Playback flags, pitch and trim extents are checked
separately. The prototype checks channel PCM and interpolation guards too.

| Check | Observed result |
| --- | --- |
| Playback matrix | 12 cases passed; 36 stock/RAM/repeat renders matched exactly. |
| PCM and guards | Exact mono and stereo channel bytes and 10-byte guards. |
| Allocation | Slot 2 selected from live bookkeeping; 24,576 bytes mono / 49,152 bytes stereo, following the untouched 8,192-byte background allocation. |
| Publication | Clear header, PCM pages, then live header; 8 transfers mono / 14 stereo. |
| No-storage path | Zero eMMC reads and writes after background setup, for both formats. RAM drive contains only the background sample. |
| Unpublished negative | Null sample pointer and silent host tap in both formats. |
| Replacement | Active unload and occupied overwrite refused; detach/unload/load/retrigger passed for both formats, with changed output and preserved background. |
| CPU integrity | No unexpected fault pages. Firmware files and pinned dependencies unchanged. |

Scoped Ruff checks and formatting pass. All **10** source harness unit tests
pass. The required [SINE replay regression](../../../out/runs/20261006T064307Z-test-c96bb1e6/manifest.json)
also passes, including its exact baseline, stock isolation, negative and
lifecycle checks. Its shared `lab/dsp.py` hash matches this run. No hardware,
commit, push or publication was performed.

The lifecycle test refuses unloading while any of the 32 voice records still
reads the sample, refuses loading into an occupied slot, detaches track 1 via
an empty-slot trigger, and executes original CPU unload/clear before loading
and playing another generation. It checks that the background allocation,
slot and PCM survive. This establishes that bounded stop-and-replace sequence;
shared references, queued events and multiple recording tracks need their own
integration work.

The unpublished-slot negative sends sample pages without the live header.
Its sample pointer stays null. The host voice-output tap emits silence when
a lane has no valid active pointer at both block boundaries, since inactive
work buffers can retain older data. The final transition block is retained.
This tap is neither the downstream mixer nor a physical audio output.

## Version and reproduction

- MAIN SHA-256:
  `57bb4dfa8df07d846adc72fdb4fb0d3cd3c5680c524bf498338460207e008e7d`.
- BLOB SHA-256:
  `0f514a12a2255f5c081e292c47f1f29462003177658da4bbae0a22fd737fffa2`.
- Clean DigiKit dependency: `277760aad51b036a4756db051409d4d3b1eeccbc`.
- Clean Selache dependency: `2b26d3b75c53063575bc5c820fa0d38879335187`.
- Stock CPU snapshot SHA-256:
  `175982f14b371fafe0eb54f2943167a94f71370327e65c7fe9941b1336bbc301`.
- Lab branch `codex/plaits-macro-controls`, base
  `c1a0ad675741339c5e154dcb5a58caa7b65b21c2`; inherited changes preserved.

Run from the machine-lab root, choosing a fresh output directory:

```sh
python3 scripts/probe-flex-lite.py out/runs/flex-lite-my-run \
  --snapshot '../Digitect firmware research project/work/digikit/snapshots/dt2-1.16/running.snap'
```

The script selects the configured Python runtime, runs `doctor`, checks the
snapshot hash, and rejects an existing output directory. Source hashes must
remain unchanged throughout the run. `--cpu-only` deliberately stops before
DSP validation and reports a different result status.

## Corrections retained from failed runs

- Slot-map index zero alone does not mean occupied: stock reset rebuilds the
  map with zero indices. The adapter checks the key and length before using
  the allocation record.
- Stock +12-semitone playback steps by `0.9999999403953552`, rather than exactly
  1.0. The pitch semantic check allows `1e-7` sample/frame rounding error. The
  RAM/file PCM comparison remains exact.
- The interpolation guard is five **16-bit samples**, or **10 bytes**, per
  channel. The initial 20-byte assumption failed. Original SHARC `0x1c400f`
  executes short-word copies at offsets 0 through 4; fresh publication agrees.
  [Retained instruction evidence](../../../out/runs/flex-lite-06/guard-instructions.json).

These are corrections to test assumptions, not changes to expected output.
Earlier failed runs remain under `out/runs/flex-lite-01` through `-05`.

## Next functional step

Connect completed recorder chunks to this owned resource, preserving the
copy-before-unlock contract recovered in [the recorder probe](FLEX-LITE-RECORDER.md).
The synthetic RAM source then becomes a real completed take. The recorder's
DSPI1 service peer remains an emulator gap; the prior synthetic service is
not evidence of real panel capture.

After that, exercise record/finish/assign/re-record through the actual panel
and sequencer path. Cancellation, empty/full capture, sample locks, machine
switching, project lifetime and optional save still need defined behavior.
SLICE/STRETCH, concurrent recording/playback, all-track operation, final output,
real-time performance and physical hardware are outside this result.
