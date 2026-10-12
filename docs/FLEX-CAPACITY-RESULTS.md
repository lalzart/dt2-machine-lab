# Flex capacity continuation results — 2026-10-08

**Implemented:** the opt-in native ownership path now streams Save As from a saved
backing file using one **32 KiB scratch allocation**. It previously copied the whole
take into RAM (a 4 MiB allocator block for 20-second stereo). RAM-backed saves keep
the existing pins and exclusive writer. Default legacy outputs remain byte-exact.
The broader identity/project-lifecycle/headroom redesign remains incomplete.

## Native behavior

`save_owned` validates a 16-byte prefix from the exact backing reference before
creating a destination. The managed raw writer then reads/writes at most 32 KiB per
iteration. Every read requires the exact stock reference-match status. Final content
hash and file length must still match the immutable descriptor before returning a
reference. A read/write/hash failure closes and deletes only the new destination,
returns scratch or pins, and preserves the old backing, descriptor and references.

The managed internal raw writer has a fourth argument: zero for resident RAM or
the scratch pointer for streaming. This API is private to the managed wrapper.
The original three-argument/default writer and instruction bytes are unchanged.
No new file is created during USE. Recorder controls and named-save UI are unchanged.

Managed code placement uses word alignment for ColdFire instructions and four-byte
alignment for long data, within the same guarded candidate padding intervals.
Stock code already has word-aligned entries such as `0x4011e87a`. Split-routine
branches remain range checked. The final image was booted and all patch bytes
were verified; exhaustive asset-path ownership and hardware remain separate gates.

## Heap facts established by native execution

**Evidence:** allocator parameters and actual malloc/free instructions establish a
32 MiB CPU arena at `0x44f39c40..0x46f39c40`, 16-byte minimum units and power-of-two
allocation classes. Descriptor blocks occupy 64 bytes. A 1,920,080-byte mono
source request occupies 2 MiB; a 3,840,080-byte stereo request occupies 4 MiB.
The exact pinned prepared snapshot starts with 28,124,192 free bytes and a 16 MiB
largest block. Those are fixture measurements, not a device-wide spare-memory promise.

The new `lab/flex_heap.py` decoder validates parameters, bucket bounds/alignment,
checksums, non-head backlinks, cycles and overlapping blocks. Native head removal
leaves a stale previous field on the new head; that field is not treated as a live
backlink. Its tracer observes original allocator entry/return instructions and
checks each successful allocation/free against actual free-list byte changes.
No allocator operation is replaced by a host model.

The stock allocation counter increments even for a failed malloc. Two forced failed
allocations left that counter two higher after every successful block was returned.
It therefore cannot serve as a live-allocation count. Flex accounting remains its
own descriptor/requested-byte accounting; decoder free bytes are computed from lists.

**Negative control:** filling 26 one-MiB blocks and freeing alternating buddies
left 14,492,704 bytes free but a largest block of one MiB. A stereo source request
failed, with no free-block mutation. All experiment allocations were then returned,
restoring the initial free block set. A corrupted free list was rejected.

**Actual Flex pressure:** this fixture accepted six distinct unsaved 20-second
stereo takes; the next native allocation failed. The candidate descriptor/source
were recovered, issued IDs/head were unchanged, and the oldest take still read exact
PCM. Saving that oldest take returned its 4 MiB block. The retry accepted a new take
at that same source address with a new identity; a retained old handle still read the
original saved PCM. This establishes recoverable source capacity within the existing
identity limit, not support for more than 32 published identities.

**Streaming under pressure:** with the six live sources restored, the largest free
block was two MiB. Backed Save As succeeded without allocating another four-MiB block.
The trace recorded a 32 KiB scratch block. Injecting an error at the second chunk
preserved the output sentinel and old reference; retrying the same filename succeeded,
proving the partial destination was removed. Forced stock sample reload matched the
complete 20-second stereo PCM. Small transient stock filesystem/loader allocations
are counted separately by the trace.

## Final validation

Paths are relative to the lab. Peripheral recorder, card, loader-event and selected
fault boundaries remain modeled; original CPU allocator/filesystem/loader instructions
execute. PCM comparisons are byte-exact.

| Gate | Final evidence | Outcome |
| --- | --- | --- |
| Allocator sizes / fragmentation / corruption | `out/runs/flex-heap-native-final/report.json` | PASS |
| Actual allocation pressure and streaming cleanup/retry | `out/runs/flex-stream-pressure-final/report.json` | PASS; full saved PCM, old handle, source reuse, 32 KiB scratch |
| 20-second mono | `out/runs/flex-stream-mono-20s/report.json` | PASS; backing mismatch/missing controls and Save As |
| 20-second stereo | `out/runs/flex-stream-stereo-20s/report.json` | PASS; same gates |
| Project save / independent stock reload / failed assignment | `out/runs/flex-stream-project/report.json` | PASS |
| Named-save UI / cancel / collision | `out/runs/flex-stream-save-ui/report.json` | PASS |
| Recorder USE / discard / replacement | `out/runs/flex-stream-use-ui/report.json` | PASS |
| 32 native accept/persist cycles | `out/runs/flex-stream-reuse-32/report.json` | PASS; source reuse, oldest PCM, 33rd rejected |
| Source suite | `out/research/flex-capacity-2026-10-08/source-tests-final-02.log` | 94 tests passed |
| Legacy stock / R3 / menu parity | `out/runs/flex-stream-package/legacy-parity.json` | PASS; exact old hashes |
| Package / instruction / repeat / menu | `out/runs/flex-stream-package/native-patches.json`, `menu-check.json` | PASS; Plaits DSP unchanged |
| Combined cold boot | `out/runs/flex-stream-boot/report.json` | PASS; 400M CPU instructions, nine tasks, all 96 native/menu writes retained; stock DSP peer |
| Stable-source SINE replay | `out/research/flex-capacity-2026-10-08/sine-frozen/out/runs/20261008T080042Z-test-6934d85c/manifest.json` | PASS; baseline, exact repeat, stock isolation, clone parity, negative control and lifecycle; stable frozen inputs |

The working-tree SINE run `20261008T075341Z-test-3dea6460` passed every behavioral
check in `result.json`, including the baseline, exact repeat, stock isolation and
lifecycle. Its outer manifest failed because unrelated Capicola contracts/scripts
changed during execution. It remains a failed provenance run. The frozen repeat
under `out/research/flex-capacity-2026-10-08/sine-frozen` preserves all 61 relevant
production/Flex/SINE/profile inputs from the recorded final source manifest.
The frozen repeat passed with unchanged source hashes. `sine-source-audit.json`
records that comparison and the unrelated changes; no
expected results were rewritten. The 94-test source-suite result belongs to its
recorded earlier source snapshot, before concurrent unrelated test edits.
After the frozen copy was taken, independent working-tree ColdFire emitter
changes also appeared. They were preserved and are excluded from this candidate's
source manifest and passing frozen replay; the audit records their hashes.

Early `flex-heap-native-01..03` failures exposed decoder assumptions about head
backlinks and the raw allocation counter; disassembly and native deltas corrected
those assumptions. `flex-pressure-native-01` used the wrong numeric error-index
assertion. Early streaming placement and test runs remain retained: the first
placement exhausted greedy padding, and pressure cleanup exceeded the old short-file
erase-model bound. A subsequent scratch-count assertion included a later stock
loader allocation; phase tracking was corrected. These are failed/incomplete runs,
not passing final evidence. The final tests retain the original deliberate faults.

## Exact build and reproduction

Local experimental package:
`out/runs/flex-stream-package/EXPERIMENTAL_PLAITS_R3_FLEX_OS1.16.syx`.

- SYX: `c01bdc72cd82a76e55ad77e4892c1a9b9e717fb70ebd84c10048ff4562eab06d`
- Combined MAIN/menu: `bc034b810768979db5459b79b05a53ea62c6411bbb07e40c3de337a0129fdef6`
- Managed stock MAIN: `562061c4c17d86d7eec0c9e12fbb3455b865131d39502128c42b39c1d573a19a`
- Pre-menu R3 MAIN: `95d0204a362f7758d3ba2a84925d55c314c024ed20bca4ca34dd5b2c25c0d6be`
- Plaits DSP: `b52b60c208cd3a9a9b88dd4db6ee0895754970cb34b48efccc2646f134159b3f`

Final source hashes are in
`out/research/flex-capacity-2026-10-08/final-source-manifest.json`.
Allocator disassembly is in the adjacent `stock-allocator.asm`.
The original source-ownership report remains a historical milestone; this report
supersedes its full-take Save As scratch requirement and final candidate hashes.

```sh
python3 scripts/check-flex-heap.py out/runs/UNIQUE
python3 scripts/check-flex-pressure.py out/runs/UNIQUE
python3 scripts/check-flex-lifetime.py out/runs/UNIQUE --managed-sources --heap-trace --frames 960000 --stereo
python3 scripts/build-flex-native.py out/runs/UNIQUE --plaits-r3 --plaits-before-midi --managed-sources --elekloader-reference out/references/elekloader-upload-audit
```

Each output must be a new ignored directory. Scripts select the pinned configured
Python and refuse an unknown firmware/snapshot. Nothing was flashed, committed,
pushed or published.

## Remaining limits

The 32 issued-identity limit remains. Neither source reclamation nor streaming
proves all old numeric handles/project references have been retired. The late-handle
source-address-reuse test makes this distinction concrete: memory can be reused
safely while identity must remain associated with the original take. A generation
lease and complete project epoch/root coverage are still needed for descriptor/ID
recycling. Unsaved samples, including inactive-pattern material, remain retained.

We now know arena size, allocation rounding and fragmentation behavior. We still
lack a measured worst-case stock-demand/headroom envelope. No independent CPU-source
budget was imposed, and six stereo takes is not advertised as hardware capacity.
A next admission experiment must cover stock project/pattern/undo/dialog/recorder
workloads and all their temporary allocations, then derive a protected reserve.
The trace exposes exact requests/occupied blocks for that work; the raw counter
must not be used as the oracle.

Physical concurrency/timing, hardware input/playback, power-loss/flush behavior,
simultaneous external backing-file mutation and exhaustive padding ownership remain
unverified. This local package retains the experimental label.
