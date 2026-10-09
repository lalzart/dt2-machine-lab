# Capicola STRETCH resource comparison

2026-10-08. Matched offline performance comparison requested by the user,
using the new STRETCH R1 backend and original stock OS 1.16 DSP.

## Scope and reproduction

The candidate keeps STRETCH ID 2. It is the already validated R1 DSP image
`2e40f16aca0243cf44732703be0e18817669ddb2ae5653c945de352ca4b3334a`.
The profiler rebuilds it and rejects any image drift. It includes the existing
Plaits R3 hook, Capicola maintenance, and the prototype's diagnostic copy of
32 samples per reader at the STRETCH destination. The comparison measures the
cost of that complete prototype against original stock DSP; it does not
attribute every extra instruction exclusively to the sparse reader.

Both images start from the same pinned stock SHFP state, process identical
captured LP0 sample transfers, and receive byte-identical adapted control wire.
The replay allocates zero-backed sample pages; Capicola additionally receives
bank backing that leaves its linked constants intact. Actual replay-image
hashes are retained separately from the original/candidate firmware hashes.
The source is the prepared 2,400-frame, 48 kHz mono click (50 ms), not a
maximum-length or maximum-density bank. Wire adaptations are explicit; no new
CPU/panel capture or physical device is involved.

The following eight scenarios are independent fresh engines:

- Idle with no STRETCH selection.
- Selection and two-pass preparation, without triggering a note.
- A trigger while preparation is pending. This must remain stock playback,
  even when the bank becomes ready; post-block destination PCM must match.
- One forward-loop track, pitch 1 and BARS 4.
- One forward-loop track, pitch 2 and BARS 1.
- Four matching forward-loop tracks, pitch 1 and BARS 4.
- Sixteen matching forward-loop tracks, pitch 1 and BARS 4.
- Sixteen shared-source tracks with varied pitch, direction and BARS.

Playback scenarios use 192 identical untriggered warmup blocks for both images,
then measure 128 blocks (85.33 ms of modeled output). The first measured block
contains the trigger; the native pipeline applies it one block later. All
subsequent custom blocks must keep two readers per requested track, and the
actual custom renderer destination must be finite and non-silent. Preparation
and pending-trigger windows contain 192 measured blocks (128 ms), including
completion and any later ready blocks. The report additionally separates the
selection-to-ready window.

Retired instructions and host microseconds cover the whole DSP block handler,
including the prototype's maintenance and diagnostic copy. DMA callbacks,
Python taps, sample loading and the playback warmup are excluded from those
block statistics. LP0/preparation costs are therefore not hidden inside the
steady-playback figures. The destination copy confirms custom signal execution;
stock post-block buffers are used only for fallback parity, not for a waveform
quality comparison. Final output, effects/level listening and physical timing
remain outside this test.

The diagnostic importer now requires equal replay initialization metadata in
addition to equal capture/state/library/firmware/boundary identities. This
prevents comparing a sample-loaded/warmed replay with the earlier pad baseline.
It shows bank-array occupancy separately from the total reservation and rejects
inconsistent accounting.

Use the configured Python 3.12 runtime from `.local/config.json` and fresh
output directories:

```sh
"/Users/lanceship/Documents/Codex/Digitect firmware research project/work/digikit/.venv/bin/python" \
  -B scripts/profile-capicola-stretch.py out/runs/capicola-resource-comparison-01

./labctl diagnostics \
  --run out/runs/capicola-resource-comparison-01 --paired-stock \
  --layout out/runs/capicola-resource-comparison-01/candidate/memory-layout.json \
  --reservation out/runs/capicola-stretch-contract-05/reservation.json \
  --output out/diagnostics/capicola-resource-comparison-01
```

`--case` can be repeated. `--blocks` permits 8–256 playback blocks; preparation
windows remain 192. Short smoke runs are retained separately and are not the
final baseline. Firmware/binaries/captures/reports remain in ignored local
output directories. No upload, package publication, commit or device operation.

## Results

The first eight-case sweep completed every playback/fallback check, but its
manifest remains failed because unrelated multi-bank-family edits changed the
shared build/layout sources during the run. Its observations are not imported
as a passing diagnostic run. A frozen source copy is prepared under
`out/runs/capicola-resource-frozen-01/source/`: the exact source hashes from the
passing R1 native report, plus this profiler and diagnostic importer. Validated
contract documents, fixture hashes and pinned dependency checks are retained.
The completed comparison is rerun there before exporting results. This is R1,
not the separate, in-progress multi-bank backend.


The final frozen R1 run passes at
`out/runs/capicola-resource-frozen-01/source/out/runs/comparison-02/`.
All sixteen per-block instruction series and every direct custom-destination
PCM file exactly repeat the first sweep. Stock active lane flags are confirmed
as 2/8/32 in the one/four/sixteen-track playing cases. All 32 custom backends
remain selected after the native trigger pipeline in the sixteen-track cases.
The first trigger block remains part of the reported mean.

| Matched workload | Stock mean instructions/block | R1 mean | R1 observed peak | Whole-block cost ratio |
| --- | ---: | ---: | ---: | ---: |
| Idle | 207,139.18 | 221,362.85 | 231,278 | 1.07x |
| Selection/preparation window | 207,438.79 | 228,791.71 | 242,926 | 1.10x |
| Unready trigger / stock fallback | 210,904.20 | 232,066.31 | 236,063 | 1.10x |
| One track, forward loop | 210,757.62 | 364,974.05 | 396,549 | 1.73x |
| One track, pitch 2 / BARS 1 | 213,002.23 | 376,494.12 | 400,015 | 1.77x |
| Four tracks, forward loop | 221,752.05 | 798,671.92 | 925,177 | 3.60x |
| Sixteen tracks, forward loop | 265,737.66 | 2,533,529.20 | 3,040,319 | 9.53x |
| Sixteen tracks, varied controls | 265,422.41 | 2,625,579.52 | 3,113,584 | 9.89x |

The current prototype is substantially more expensive than stock as active
readers increase. These are whole-block costs: roughly +73% for one ordinary
looping track, +260% for four and +853% for sixteen. The varied sixteen-track
case reaches +889%, with a 3,113,584-instruction peak. Earlier 40.5% playback
optimization was a comparison with the previous Capicola implementation, not
with stock STRETCH. It should not be read as a claim of stock-level efficiency.

The 50 ms source becomes ready after **153 blocks**, corresponding to 102 ms
of modeled audio-block time. In that selection-to-ready window, stock averages
207,436.95 instructions/block and R1 230,705.19; the total difference is
3,560,041 retired instructions, about +11.22%. The 192-block table row also
includes ready-idle blocks. These are scheduling observations, not actual
hardware preparation latency. The pending-trigger destination remains exactly
stock, with no mid-note takeover.

The prepared bank contains **230 keys** and **2,760 bytes of allocated arrays**.
All 32 reader records total **4,224 bytes**; matching tracks share one bank.
There is also a 32-byte bank descriptor. These occupy parts of the **8 MiB total
reservation**, alongside working memory. They do not multiply the reservation
by track count. The reserved working span is 200 KiB; this candidate has 78,766
instruction bytes and 12,496 linked constant bytes. The original source PCM
remains in the sample pool. The maximum twelve-second bank can require
6,912,048 bytes, so this tiny click is not a representative memory-capacity
stress case. The CPU reservation declaration leaves 392 MiB sample capacity;
this test does not run or measure a new CPU heap workload.

A next performance experiment should profile the reader/splice paths and
measure sustained longer/dense samples, while retaining the exact destination
PCM and transport oracles. This comparison does not establish hardware
headroom, subjective quality, final output, stereo support or performance of
the separate in-progress multi-bank backend.

## Validation and screen

The complete comparison passes source stability and fixture/image hash guards.
It includes 16 DSP profiles, exact pending-trigger fallback destination parity,
finite/nonzero actual custom destination output, matching active lane counts,
and exact repeated instructions/custom PCM. The current configured-runtime
source suite passes **129 tests**; the 16 focused diagnostics/workload tests
also pass after the screen formatting change. Ruff and `git diff --check` pass.
No shared DSP instruction/runtime implementation was changed by profiling;
the validated R1 source's existing SINE regression remains the prior adapter
regression evidence.

The screen is in `out/diagnostics/capicola-resource-comparison-01/`, with an
eight-row matched comparison, all 16 raw profiles, shared-bank memory,
placement and reservation declarations. Browser review verifies the displayed
ratios and measurement scope. To regenerate this exact saved screen:

```sh
./labctl diagnostics \
  --run out/runs/capicola-resource-frozen-01/source/out/runs/comparison-02 \
  --paired-stock \
  --layout out/runs/capicola-resource-frozen-01/source/out/runs/comparison-02/candidate/memory-layout.json \
  --reservation out/runs/capicola-stretch-contract-05/reservation.json \
  --output out/diagnostics/<fresh-name>
```
