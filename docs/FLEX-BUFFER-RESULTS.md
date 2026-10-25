# Flex recorder destinations and reusable buffers — results

Latest increment: [native queued BUF recorder worker](RECORDER-WORKER-NATIVE.md)
executes capture-copy, stock loading, generation registration and final-header
publication as ColdFire instructions. Its bounded ownership and remaining
FREEZE/readback/device gates are documented separately; the earlier host
prototype described below is preserved.

Digitakt II **OS 1.16**, 2026-10-20. The isolated emulator prototype works through
the original recorder panel and sample selector. It is opt-in and does not
change normal firmware builds. No firmware was packaged for installation,
uploaded, flashed, committed or published.

## What works

The ready recorder page has **DEST = TAKE / BUF 1–4** on C. MON stays on E,
with its original cell and setter. The test changes the actual stock monitoring
value from 0 to 1 without changing DEST. Capture, waveform display, E/H trim,
USE and discard use the original recorder view. USE to BUF 1 assigns the
selected ONESHOT track; the stock selector can independently assign that same
BUF 1 to another track. Re-recording changes its physical generation while
both tracks retain the same visible sample number. BUF 2 is independent and
TAKE still creates an independent temporary sample.

Original SHARC execution confirms that tracks **1 and 5** match ordinary file
loading exactly. Publishing replacement B leaves active A voice pointers and
output unchanged; later triggers acquire B. Old allocations remain pinned.
**Safe indefinite reclamation and native SAVE remain unresolved.** The
prototype refuses additional work at a fixed limit, and guards project save
and the tested public project-load API. These boundaries are part of the
prototype, not completed target firmware features.

See [UI and workflow](FLEX-BUFFER-UX.md),
[resource architecture](FLEX-BUFFER-ARCHITECTURE.md), and the preceding
[DSP memory investigation](FLEX-DSP-MEMORY-INVESTIGATION.md).

## Implementation and evidence layers

| Layer | Implemented and exercised | Limits |
| --- | --- | --- |
| ColdFire guest instructions | Emitted ready/armed C dispatch and DEST draw/value/setter; original MON paths retained byte-for-byte. Actual original recorder and selector code runs. | Code/state occupy explicitly host-mapped scratch at `0x10300000`; no target placement or native feature build. |
| Original CPU loader | Original extent allocation, bounded reads, stereo packing, page/header construction, cached-key alias publication, track assignment and selector navigation. | WAV recorder peer, resource reads, locks/peripheral endpoints, transaction scheduling and volatile names/guards are host adapters. |
| Original SHARC | Original page/header callback, guard construction, sample descriptors and ONESHOT render. Exact two-track voice-PCM comparison with ordinary file loading. | Separate buffered replay, host-delivered pages/control frames; not coupled real-time CPU/DSP audio or physical DMA/cache timing. |
| Host lifecycle oracle | Four logical identities, immutable generations, candidate tickets/epochs, byte/generation admission, cancellation, failure quarantine and project guards. | No native active-reader accounting, reclamation, reverse transfer or complete root/undo/project audit. |
| Device | None. | No physical input, listening judgment, audio deadlines, hardware controls or installed-firmware behavior verified. |

New source files:

- `lab/flex_buffer_core.py`: immutable tickets/generations and bounded resource contract.
- `lab/flex_buffer_ui.py`: opt-in original-panel integration and host publication.
- `scripts/try-flex-buffers.py`: interactive launcher and reproducible panel workflow.
- `scripts/check-flex-buffer-audio.py`: original CPU/SHARC comparison oracle.
- `tests/test_flex_buffers.py`: eight lifecycle tests, including all four destinations.

All **552** pre-existing executable files from the prior DSP investigation's
source manifest still hash identically. The buffer prototype adds only the
four Python modules/scripts listed above. The C revision changes only
`lab/flex_buffer_ui.py` and its `scripts/try-flex-buffers.py` workflow; the
generation model and audio checker remain identical to the initial prototype.
The ordinary unit-test file is hashed separately in final verification.
This preserves the inherited dirty native Flex, Plaits, Capicola, build scripts
and pinned dependencies; it does not claim a new combined-feature runtime test.

## Actual OLED captures

The rasters are 128×64 and use stock typography/draw routines. Native ready
cell and event addresses are recorded in the [UI audit](FLEX-BUFFER-UX.md).

| Stock ready page | DEST on C, stock MON on E |
| --- | --- |
| ![Stock recorder](../out/runs/flex-buffer-ui-audit-20261020-01/stock-recorder.png) | ![BUF 1 destination](../out/runs/flex-buffer-c-workflow-20261020-02/02-dest-buf1.png) |

| Original trim view | Original selector, four stable buffer rows |
| --- | --- |
| ![Trim](../out/runs/flex-buffer-c-workflow-20261020-02/04-trim.png) | ![Buffer rows](../out/runs/flex-buffer-c-workflow-20261020-02/06b-buffer-rows-in-stock-selector.png) |

The selector screenshot shows `044 BUF 1 READY` and `045–047 BUF 2–4 EMPTY`.
The workflow reaches these rows using stock bank and cursor navigation, then
YES assigns BUF 1 to T5. It does not write T5's sample assignment from the host.
USE autoassignment uses the existing helper, which verifies other track bytes
are unchanged. The initial selector viewport can show cached previous names
until ordinary navigation refreshes it; the captured navigated view is the
validated buffer selection. Private generation rows do not acquire take names.
Individual update captures can also contain only a subset of ready-page cells;
this was reproduced with ordinary E events in the untouched-stock control at
`out/runs/flex-buffer-c-stock-monitor-20261020-01/`. The full setup frame above
is the display comparison. Monitoring behavior is checked through the original
getter, not inferred from the completeness of one update screenshot.

## Reproduction and final runs

Run from `dt2-machine-lab`. The scripts re-exec the configured Python 3.12,
verify pinned inputs and refuse an existing output directory. Choose fresh
output names to repeat these exact commands.

```sh
python3 scripts/try-flex-buffers.py out/runs/flex-buffer-c-workflow-20261020-02 --check
python3 scripts/check-flex-buffer-audio.py out/runs/flex-buffer-c-workflow-20261020-02 out/runs/flex-buffer-c-audio-20261020-01
python3 scripts/try-flex-buffers.py out/runs/flex-buffer-c-window-20261020-01 --window-seconds 10
"/Users/lanceship/Documents/Codex/Digitect firmware research project/work/digikit/.venv/bin/python" -m unittest discover -s tests -v
./labctl test sine --replay
```

For the interactive workflow use `python3 scripts/try-flex-buffers.py` without
`--check`. Default window lifetime is fifteen minutes, bounded by
`--window-seconds 10..1800`. The existing WAV chooser and buffered audition are
available. Buffer USE accepts at most two seconds. C uses the stock encoder
scaler, so several small host encoder events can yield no destination step.

The final panel report is
[`flex-buffer-c-workflow-20261020-02/report.json`](../out/runs/flex-buffer-c-workflow-20261020-02/report.json).
It records all events, slot/allocation identities, trim values, page history,
actual DSPI2 pad captures, input hashes, initial Git status, branch/HEAD and
source fingerprints. The complete executable source set is copied into
`frozen-sources/`; source drift fails the run. The final audio report is
[`flex-buffer-c-audio-20261020-01/report.json`](../out/runs/flex-buffer-c-audio-20261020-01/report.json)
and hashes the panel report. The ten-second window smoke test passed without
guest fault pages; it establishes window operation, not a second manual workflow.

Final verification is retained in
[`verification.json`](../out/runs/flex-buffer-c-workflow-20261020-02/verification.json).
`doctor` passed; **293 source tests** passed, including eight new buffer tests;
Ruff lint/format checks passed on all five new Python files. The required SINE
replay [passed](../out/runs/20261020T102540Z-test-dcbccbee/manifest.json), with
the same 556-entry frozen source set. The panel, audio and window runs all
passed without source drift. Existing expectations were not regenerated.

### Provenance

Branch `codex/plaits-macro-controls`, HEAD
`77b1c2a1746a355b66b1a7e1cb61939c9bc0fdb5`, with inherited staged, unstaged
and untracked work. HEAD alone is not the tested source identity.

| Input | Revision or SHA-256 |
| --- | --- |
| Clean pinned DigiKit | `277760aad51b036a4756db051409d4d3b1eeccbc` |
| Clean pinned Selache | `2b26d3b75c53063575bc5c820fa0d38879335187` |
| Original 1.16 SYX | `278541e466edcd77d6b3e018a91fb90185932d3c7de224dd3e68294dddf3a9ec` |
| Original MAIN | `57bb4dfa8df07d846adc72fdb4fb0d3cd3c5680c524bf498338460207e008e7d` |
| Original SHARC BLOB | `0f514a12a2255f5c081e292c47f1f29462003177658da4bbae0a22fd737fffa2` |
| GUI snapshot | `3852f53c7e45c358702ed9cefb8bb3ef2af194f4f501e70b6cfbcba333494867` |
| Matching GUI LP0 feed | `3a71cae37303d089fe68c44679d664b26237788e4eb21d932ec13f9a7716eaa8` |
| Workflow source-manifest file | `2ba2190a13fb07031e7f6a96126ef1fd8e02e84a2bed44d855f6cb8ff819df60` |
| Workflow report | `c473f86ce626dcf26d20a92d6dfc6a1b8eab70aff6da2de98ff2524d06914710` |

### Workflow observations and negative controls

| Check | Observed result |
| --- | --- |
| DEST / MON | BUF 1 selected by actual C events; unmodified E changes stock monitoring 0→1 without FUNC; DEST stays 1. Repeated recorder visits preserve selection. Original MON draw, label and setter bytes match stock. |
| Trim and USE A | Candidate `[0,3136)` trimmed by original E/H to `[86,3050)`, 2,964 stereo frames. Visible slot 300, private 1023, generation 1, extent `0x2400`, 16 KiB. |
| Manual shared selection | T5 selects numeric slot 300 through SRC/D-push/bank/cursor/YES; T1 remains 300. All four named rows were drawn by the original selector. |
| Re-record BUF 1 | Generation 2, 3,120 stereo frames, private 1022, extent `0x6400`, 16 KiB. Both live tracks remain slot 300. A's extent is distinct and pinned. |
| BUF 2 | Generation 3, 3,136 frames, visible 301, private 1021, extent `0xa400`, 16 KiB; BUF 1 remains unchanged. |
| Discard | Normal FUNC+NO preserves previous BUF 2. |
| Return to TAKE | Independent `TEMP001`, slot 304, 3,120 frames. Existing host source retained. |
| Allocation failure | Named host fault before loading: USE remains in trim, committed BUF 2 unchanged. |
| Incomplete publication | Named host fault after private loading, before alias publication: old BUF 2 unchanged; failed allocation/identity quarantined and counted. |
| Exhausted byte budget | Lowered admission budget to occupied bytes; new USE rejected, old BUF 2 retained. Unit test also exercises generation-count exhaustion. |
| Empty | Unpublished BUF 4 produces silence in original ONESHOT replay. Selector shows EMPTY. |
| Stale handles / premature reuse | Cancelled candidate cannot commit after a new ticket; stale epoch and duplicate generation rejected by host tests. No old generation is reclaimed or overwritten. |
| Project save | Original `0x40043a30` entry called; host guard returns failure before writes. No synthetic references serialized. |
| Project transition | Original public `0x400f5050` storage-load entry returns failure before decode/reset. Separate host epoch test clears logical refs/DEST and refuses further buffer recording. Actual project switching is not implemented. |
| File activity | Zero modeled +Drive/eMMC writes during the panel workflow. Test inputs/artifacts are host files. |

The deterministic stereo fixture is generated in the launcher: 12,000 frames
of distinct modular ramps per take, 48 kHz PCM16. Simulated recording duration
uses stock tick/frame requests, so the accepted short candidates above are
about 62–65 ms. It is not a two-second recording test. The original chunk API's
bytes must match the selected/trimmed fixture before loading. Larger two-second
publication was separately exercised by the prior DSP memory probe.

### Audio comparison

The checker reconstructs accepted PCM from captured stock pages, loads the
same material as ordinary WAV/native samples through the unmodified CPU file
loader, and runs original SHARC callbacks/renderers for both. Its two-track
control frame comes from the real CPU pad capture; trigger bits are explicitly
set for T1/T5 in this comparison. This is not a sequencer-pattern recording
demonstration. Each measured lane is nonzero and finite, preventing silent
parity from passing. Comparisons use exact float bytes from the voice work
buffers, decimated by the established 64→32 sample adapter.

| Phase | Blocks | Result |
| --- | ---: | --- |
| A, shared by T1/T5 | 24 | Exact ordinary-loading output on both tracks. |
| Publish B while A plays, no retrigger | 16 | Old installed pointers unchanged; exact continuing A output. |
| New triggers after publication | 32 | Exact ordinary-loading B output on both tracks. |
| Empty BUF 4 | 12 | Both tracks silent. |

Raw four-lane `.f32` captures and per-track stereo WAVs are in the audio run,
including [A on T1](../out/runs/flex-buffer-c-audio-20261020-01/a-shared-t1.wav),
[continuing A after B publication](../out/runs/flex-buffer-c-audio-20261020-01/old-readers-after-b-publication-t1.wav)
and [replacement B on T1](../out/runs/flex-buffer-c-audio-20261020-01/new-triggers-use-b-t1.wav).
These short correctness windows are voice taps, not final DAC-facing output
or a musical listening evaluation. The old-reader test is bounded to the
observed active interval; it does not prove a native retirement barrier.

### Resource accounting

The complete panel run retains four buffer allocations: three successful
generations and one deliberately failed private publication, each 16 KiB,
**64 KiB total**. Five identities were issued including TAKE; failed identities
are never reused. One independent host TAKE source remains; successful and
failed BUF source entries are removed with no open source handles. No full BUF
PCM allocation is made in the guest CPU heap. Host input WAV/test page history
remain host-owned. The `guest_cpu_buffer_sources: 0` report field describes this
adapter's allocation policy; it is not a whole-heap/free-RAM measurement.

Admission limits are eight private generations, 4 MiB and 32 total issued
synthetic identities. Four visible aliases plus eight private ownership slots
are reserved only after checking both CPU loader state and project entries.
At the two-second stereo ceiling each stock extent is 385,024 bytes, so eight
such extents use 3,080,192 bytes before stock metadata. A full session must be
restarted when limits are reached. CPU instruction overhead, native publication
latency, fragmentation under full projects, hardware bandwidth/cache behavior
and audio deadlines are not measured by this UI experiment. See the earlier
DSP investigation for its separately labeled publication/instruction estimates.

### Failed development controls retained

Earlier ignored runs are preserved, not regenerated into expected results.
Initial emitter smoke checks rejected an unaudited ADDQ encoding; it was replaced
with audited ADDI. An incorrect draw-stack adjustment trapped in the original
firmware; the final hook preserves the original reusable stack argument.
Workflow runs 01–03 rejected the MON check because small FUNC encoder deltas
were rounded to zero by the original scaler; the final test uses larger deltas
and checks the original getter. Runs 04–06 passed behavioral assertions but
visual QA found overlapping MON/DEST labels and a stale initial selector view.
The initial E layout then passed with the original label call and explicit
checks for all four selector strings. It is preserved in the earlier run. The
current C layout replaces only the C prompt graphic and removes the MON/FUNC
trampolines. Its first run rejected an unaudited TST.B encoding before guest
execution; the correction masks the byte-sized predicate using audited ANDI.L.
The final C run checks the original MON code ranges as well as behavior.
The visual defects were not accepted based solely on a green behavior report.
The first C SINE replay was invalidated by the instruction-audit correction
changing its frozen source; that failed provenance run is preserved separately.
The final replay uses the completed C source and passes without drift.

## Remaining boundaries and next implementation

Native deployment stops at **reader lifetime, acknowledged publication and
readback**. The host transaction/pins are not replacements for these protocols.
No backing address, sample identity or Capicola memory is recycled. Normal
project-save persistence cannot silently retain volatile synthetic keys.
Post-USE source reopens, waveform/editor/normalize/export/reload behavior and
non-ONESHOT readers are not established; a SRC waveform can be blank without
a reopenable source. The recorder's candidate trim waveform is verified.

1. Port the small C/DEST UI seam to audited native placement/state, preserving
   this panel contract. Add original OLED errors for full/empty/volatile states.
   Keep the existing native 20-second TAKE path as the compatibility control.
2. Implement a native generation descriptor and four logical aliases, with
   native slot reservations and explicit exclusion of Capicola's region on every
   allocator path. Start with the same bounded, never-reclaimed generations.
3. Publish to an inactive allocation and add a DSP acknowledgment after final
   data, guards and header. Make logical replacement and failure rollback an
   actual protocol; inject failures at the alias/assignment boundary.
4. Trace all ONESHOT readers, queued triggers, locks, pattern/kit/undo/clipboard
   roots and project reset. Add generation leases and quiescence tests before
   freeing any allocation or recycling an identity. Native save/load menus and
   epoch transitions must participate before permitting project switches.
5. Add bounded native DSP readback and verified native SAVE. FREEZE can then pin
   the current immutable generation as a separate sample root. Audit other
   machines independently, especially granular windows and Capicola caches.
6. Only after those gates pass, evaluate real input/internal-mix capture,
   sequencer-triggered recording, real-time deadlines and a separately authorized
   device trial. This task supplies no hardware installation artifact.
