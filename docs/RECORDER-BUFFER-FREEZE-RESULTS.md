# Recorder buffers: bounded FREEZE evidence

2026-10-20, Digitakt II OS 1.16. Product decisions and migration gates are in
[RECORDER-BUFFER-PRODUCT-HANDOFF.md](RECORDER-BUFFER-PRODUCT-HANDOFF.md).

**Result:** a completed DSP-backed buffer can acquire a distinct immutable
sample slot through the stock CPU loader's cache path, with no PCM pages or
retained source PCM. After re-recording BUF 1, T1/T5 play the new version and
T6 plays the frozen original exactly against ordinary-file stock output.
This is a host-orchestrated emulator proof, not native FREEZE firmware or an
installed shortcut. All generations stay pinned; safe reclamation is unsolved.

## Sources and provenance

Branch `codex/plaits-macro-controls`, HEAD
`77b1c2a1746a355b66b1a7e1cb61939c9bc0fdb5`, plus the inherited dirty tree.
No existing source, build script, dependency, historical report or baseline
expectation was changed. The audit froze 556 existing sources and verified
that they matched the latest passing encoder-C workflow. The successful new
probe froze 560 sources: those 556 plus these four opt-in files:

- `lab/flex_freeze.py`: metadata-only cache resolution, immutable snapshot
  descriptor, new slot/name, save/load protection and bounded admission.
- `lab/flex_freeze_probe.py`: ordinary-file/stock-SHARC audio oracle.
- `scripts/probe-flex-freeze.py`: original recorder/selector panel workflow,
  negative controls, repeated generations, accounting and audio comparison.
- `lab/flex_quick_record.py`: isolated arm/start/stop/publication contract.

`tests/test_flex_quick_record.py` adds three scheduling/epoch scenarios.
Test files are separately hashed in the probe's `test-sources.json`, since
the repository's standard source manifest excludes most unit-test sources.

DigiKit: `277760aad51b036a4756db051409d4d3b1eeccbc`.
Selache: `2b26d3b75c53063575bc5c820fa0d38879335187`.
`./labctl doctor` passed. Authenticated stock fixture hashes include:

| Input | SHA-256 |
| --- | --- |
| MAIN | `57bb4dfa8df07d846adc72fdb4fb0d3cd3c5680c524bf498338460207e008e7d` |
| GUI checkpoint | `3852f53c7e45c358702ed9cefb8bb3ef2af194f4f501e70b6cfbcba333494867` |
| GUI card | `f0a30d418c256ad2d8a87c395a36ffbce2fb8ad0119d755927b442f77df28cea` |
| GUI LP0 feed | `3a71cae37303d089fe68c44679d664b26237788e4eb21d932ec13f9a7716eaa8` |
| File-oracle CPU checkpoint | `175982f14b371fafe0eb54f2943167a94f71370327e65c7fe9941b1336bbc301` |

Successful artifact directory: `out/runs/flex-freeze-20261020-03/`.
Report SHA-256:
`3882fccd055aec8a10195365c08d2d7475387cca0b4f733bc95a4fc8b2ad96ae`.
`sources.json` SHA-256:
`241d3caed48c4f6dafc25bcea51b8600ce12c29f8defa6d8a3a226edd6bfd9f6`.
The run contains frozen source copies, page histories, actual panel-trigger
control frames, input hashes, screenshots, float PCM and per-track WAVs.

## Reproduce

Use a fresh output path; the script refuses to overwrite a run. It uses the
configured Python 3.12 automatically, authenticates fixtures and leaves normal
firmware builds untouched. From the repository root:

```sh
./labctl doctor
python3 scripts/probe-flex-freeze.py out/runs/flex-freeze-new
"/Users/lanceship/Documents/Codex/Digitect firmware research project/work/digikit/.venv/bin/python" -m unittest discover -s tests -v
./labctl test sine --replay
```

Private stock fixtures and the existing local DSP runtime are required. Test
WAVs/cards created in `ordinary-reference-only*` are explicitly ordinary-file
comparison fixtures; they are not used to implement buffer storage or saving.
Capture input and page histories are retained on the host for reproducibility.
The native recorder producer and physical transport remain modeled boundaries.

## What executes

The probe uses the original sampling page. C selects BUF 1; original YES
start/stop and E/H trim yield 2,948 stereo frames, trimmed from [0,3120) to
[86,3034). USE calls the existing buffer adapter and original stock loader.
It removes the host source PCM entry after complete publication.

FREEZE is invoked by a test command at a paused performance/SRC boundary.
No physical chord or alternate recorder page is installed. It creates
**B1-001**, visible in the stock sample selector, with a new project identity
and a distinct sample slot. It does not change any track assignment. T5 then
selects BUF 1 and T6 selects B1-001 through actual panel events and original
selector handling. The T6 selection is checked in a real CPU-produced DSPI2
control frame, not only in host metadata.

Re-recording BUF 1 produces 3,120 frames at a different allocation. T1/T5
still select slot 300 and T6 still selects 304. Eight complete recordings and
eight freezes are exercised, followed by safe refusal of a ninth. No +Drive
writes occur in the workflow card overlay.

| Object | Slot / identity | Backing |
| --- | --- | --- |
| Logical BUF 1 | Slot 300, project `0x7ffd0001`, epoch 1 | Changes after completed USE |
| First private generation | Slot 1023, loader key starting `0x7ffe0001` | Logical start `0x2400`, 16,384 bytes |
| Frozen B1-001 | Slot 304, project `0x7ffc0001`, epoch 1 | Same block index/start/size as generation 1 |
| Second private generation | Slot 1022, loader key starting `0x7ffe0002` | Logical start `0x6400`, 16,384 bytes |
| Later snapshots | Slots 305–311, project identities `0x7ffc0002`–`0x7ffc0008` | Their individual immutable generations |

The snapshot's **project identity differs from its CPU loader content key**.
The latter must continue identifying the existing cache entry. A metadata-only
provider supplies the original key/name; its `data` access deliberately raises
an error. Deleting PCM and then calling the ordinary resolver without this
provider fails, as the negative control demonstrates. This bridge is a host
callback, not an implementation of the native volatile resource resolver.

## Exact stock audio comparisons

Ordinary reference files are built from the captured deterministic PCM, read
by the unmodified CPU file loader and published through original SHARC LP0
callbacks. The comparison runs original ONESHOT rendering using the captured
track parameters. Harness code selects trigger bits and slot references to
exercise three tracks together. Audio is tapped at voice work buffers and
decimated as in the existing oracle; this is not the final DAC mix.

| Phase | Blocks, 32 frames at 48 kHz | Result / SHA-256 of six-lane float output |
| --- | --- | --- |
| A on BUF and frozen sample | 12 | Exact, nonzero: `802a602f0d4c9a06c8c00ea134a8fca770892e43bc1911d2b9f75f48901a1de0` |
| Active A while B is published | 12 | Exact, nonzero: `0c53b6f0ebec19ef48b3dbc75923344f6e328606329aa46cc43c82182213fb29` |
| New triggers: T1/T5=B, T6=A | 40 | Exact, nonzero: `00f5df269b0a1883926bdb6bf99cc553de99ca6999b41f54b682347703b5360d` |
| Late T6 retrigger after eight generations | 24 | Exact, nonzero: `f9e08b7a9d469461a344248279008d4d084c34da2165881eeef7c9fbd6b2664a` |

During B publication all six active channel pointers remain unchanged:
`0x8422d9e8`, `0x8422f9e8` for T1, T5 and T6. Subsequent buffer triggers resolve
B while the frozen slot still resolves A. These are bounded voice comparisons,
not a long-duration loop/end-of-reader or simultaneous hardware timing test.

## Memory, publication and limits

Each freeze has **zero PCM data pages**, no source open/read, unchanged stock
allocation-vector extent and identical original/frozen allocation indices.
It emits two 4 KiB slot headers: invalid/clear followed by the completed header,
about 8,200 transport bytes including tags. The new logical sample is exposed
only after completion. This is measured sharing of existing PCM backing for
the tested cache-hit operation. It is not a general zero-copy capture claim.

The heap decoder measures **32 bytes less free CPU heap per freeze**, consistent
with the stock per-slot association node (`0x14`-byte request at loader
`0x40154696`; buddy allocation rounds it). These are metadata allocations,
not sample-sized PCM copies. Across all eight freeze operations that is 256
bytes. The overall free heap also changes between panel/recording actions;
do not attribute all of that change to FREEZE.

| After recording/freezing generation | Retained DSP allocation bytes | Source PCM entries | Free heap after freeze |
| --- | --- | --- | --- |
| 1 | 16,384 | 0 | 28,108,544 |
| 2 | 32,768 | 0 | 28,107,664 |
| 4 | 65,536 | 0 | 28,107,232 |
| 8 | 131,072 | 0 | 28,106,496 |

Largest free CPU heap block remains 16 MiB at those boundaries. Freeze host
transaction/inspection time was 5.72–7.14 ms; it includes Python and emulation
overhead and is **not** a target latency or SHARC cycle measurement. No CPU
PCM allocation is made by this host-backed buffer source adapter; this is
different from measuring native source free, which the earlier DSP probe did.

One slot is consumed per frozen snapshot; one private slot/native source
identity per recording generation. BUF rows remain four stable slots. This
run uses eight recording identities plus eight distinct snapshot identities,
not a recycled identity namespace. Limits remain eight generations, eight
snapshots, 4 MiB admission and two seconds per BUF candidate. There is **no
memory plateau or indefinite reuse**: every old generation is quarantined.
All observed allocations end below logical `0x18800400`; Capicola's separate
8 MiB reservation is untouched. No new reservation was made.

Capacity estimates below use 48 kHz PCM16 and the observed loader expression
`(PCM bytes + 80 + 0x200f) & ~0x1fff`. These are arithmetic estimates, not new
long-capture or hardware measurements:

| Duration | Mono PCM / estimated allocation bytes | Stereo PCM / estimated allocation bytes |
| --- | --- | --- |
| 2 s | 192,000 / 196,608 | 384,000 / 385,024 |
| 10 s | 960,000 / 966,656 | 1,920,000 / 1,925,120 |
| 20 s | 1,920,000 / 1,925,120 | 3,840,000 / 3,842,048 |
| 60 s | 5,760,000 / 5,767,168 | 11,520,000 / 11,526,144 |

Stereo capture alone is 192 kB/s; simultaneous loading, reads, conversion,
guards, FX and other voices add traffic. DDR capacity/specification does not
establish board bandwidth, cache coherency, DMA completion or deadline safety.
The previous [DSP investigation](FLEX-DSP-MEMORY-INVESTIGATION.md) remains the
version-scoped allocation/transport/capture-tap audit.

## Negative controls and failed runs

Passed negatives: empty BUF; stale epoch; missing retired-source metadata;
injected snapshot admission failure; candidate allocation failure; discard;
ninth-snapshot and ninth-generation rejection; missing readback for all eight
sources; guarded project save/load; and rejection after modeled project epoch
change. Existing committed buffer and frozen assignments survive rejection.
The earlier encoder-C run separately exercised incomplete publication and
quarantining its allocation; `tests/test_flex_buffers.py` covers incomplete
and stale publication. No native callback is claimed to implement these
fault-injection seams.

Two initial runs are retained, not rewritten:

- `flex-freeze-20261020-01`: alternating small E/H turns did not move both
  trim endpoints. No FREEZE/audio result. Driver now uses the earlier passing
  sequence: advance E until start changes, then H until end changes.
- `flex-freeze-20261020-02`: overstrict all-16-bytes-invalid test rejected an
  empty project slot. The stock empty sentinel is its identity word; trailing
  fields are not necessarily erased. The corrected chooser checks **both**
  loader emptiness and invalid project identity. It does not appropriate a
  loader-empty slot that has a live project identity.

Late failures after alias publication/track or project-reference updates are
not fully rolled back by this experiment. Native I/O failure, IRQ races and
resource pressure must not be inferred from a pre-publication host fault.

## Screens and acceptance status

Actual 128×64 OLED captures, exported at integer scale, in the successful run:

- `01-dest-buf1.png`: C DEST, original E MON and other recorder controls.
- `02-trim-a.png`: original trim view with USE convention.
- `03-freeze-from-performance-context.png`: unchanged performance/SRC context.
- `selector-t6.png`: BUF 1 READY, BUF 2–4 EMPTY and B1-001 in stock selector.
- `04-frozen-snapshot-on-t6.png`, `05-buf1-rerecorded-t6-still-frozen.png`.

For stock comparison use
`out/runs/flex-buffer-c-stock-monitor-20261020-01/stock-before-monitor.png`;
the earlier buffer report documents stock panel-latching limitations. No
new screenshot pretends that NORMAL, an arm indicator or a FREEZE chord is
implemented. Frozen registration is in the project pool and selector; the
full Project RAM management page has not been exercised here.

| Acceptance scenario | State |
| --- | --- |
| A NORMAL full stock save/assign | Unmet in buffer adapter; original source preserved, migration gate explicit |
| B buffer record/trim/USE | Executed on original panel |
| C shared buffer | T1/T5 assignment, replacement and exact voice output executed |
| D FREEZE and continue | Executed via host command and original selector; gesture still unbound |
| E quick recording | Three isolated state tests; panel shortcut/bar hook unimplemented |
| F repeated operation | Eight cycles and graceful refusal; no reclaimer/plateau |
| G native Save/reload | Unmet: native DSP→CPU readback unresolved |
| H edge cases | Listed negatives executed; pending trigs, sample locks, all pattern/clipboard roots and real project transition unresolved |

`out/recorder-handoff-unittest-20261020-01.log`: **296 tests passed**.
Ruff check and format check pass for the five new Python files. SINE replay
and final preservation verification are recorded alongside the run in
`verification.json` after completion.

SINE replay passed at `out/runs/20261020T114719Z-test-fdbf4ee2/manifest.json`
with the same 560 source hashes as the successful FREEZE probe. A final unit
run after the slot-chooser correction is retained in
`out/recorder-handoff-unittest-20261020-02.log`.

An additional negative audio oracle deliberately redirects frozen slot 304 to
the latest BUF 1 generation in a cloned DSP state. The resulting T6 PCM
differs from the correct frozen A, so an implementation that merely follows
the buffer cannot pass this comparison. It passes in
`out/runs/flex-freeze-wrong-generation-20261020-02/report.json`; the 24-block
correct output hashes to
`895f82be8910481f5a090ae0d3199c704e17ef5a2de0eaba0e4b4c10711948dc`.
The reproducible control script is preserved with the successful run:

```sh
"/Users/lanceship/Documents/Codex/Digitect firmware research project/work/digikit/.venv/bin/python" out/runs/flex-freeze-20261020-03/check-wrong-generation.py out/runs/flex-freeze-wrong-generation-new
```

This optional artifact-local script requires the preceding workflow artifacts.
Its first invocation stopped at the runtime guard because no output run was
allocated; `out/flex-freeze-wrong-generation-20261020-01.log` preserves that
startup failure. The corrected script allocates a fresh run before DSP import.

## Remaining integration gates

Stock cache aliases are useful, but private generation pins remain present in
this proof. It does not prove that a frozen slot alone accounts for every
reader/root or that removing the final alias safely frees backing. Do not
drop those pins, compact allocations or reuse identities based on this result.

Native Save and project durability still need bounded readback or another
proven source strategy. The metadata provider cannot reopen PCM; the native
size call fails deliberately. Earlier host-assisted readback through the stock
writer does not satisfy that transport dependency.

Prioritize restoring genuine NORMAL routing, then native metadata-only aliases
and save/load guards, then an audited fast gesture. The next musical feature
after that is quick arm using an authoritative sequencer boundary and complete
publication acknowledgement. Reader/root retirement and native saving are
separate required increments. Preserve the current 20-second Flex/native save
implementation until those gates and its regressions are satisfied. No device
image, upload, flash, commit or publication was performed.
