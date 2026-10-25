# First post-boot BUSY refusal — OS 1.16

The user reports `BUSY FREEZE 1` on the first ARM attempt after a full power
cycle and starting playback. A later attempt can reach `REF CLOCK 0`.
`REC READY / BUF IDLE` describes the recorder and BUF transaction; it does not
establish that the shared stock sample-operation guard is idle. The startup
refusal is the primary issue. The physical cause is still unconfirmed.

Device follow-up: after flashing this sample diagnostic, the user reports
successive `BUSY LOAD 259`, `BUSY LOAD 261`, and `BUSY LOAD 262` refusals while
the sequencer is running. Those slots also occur in order in both saved native
startup traces, called from return PC `0x4004eaae`; the fixture later finishes
loading and reaches count zero. Changing slot numbers support advancing stock
sample loads rather than one permanently held operation. The hardware's actual
caller, current project contents and elapsed time since power-on remain unknown.
The refused ARM path checks this guard before setup/admission/queueing, so these
attempts do not submit recording jobs. No firmware change or new capture is
needed to establish this source/trace correspondence.
[Matching slot evidence](../out/runs/sketch-load-slots-20261023-01/followup.json).

The user subsequently waited and reached `REF CLOCK 0` with playback running,
confirming that this loading block clears in that device trial. Clock work
resumes in the separate [clock correction candidate](SKETCH-CLOCK-CORRECTION.md);
this original sample-diagnostic package remains unchanged.

## What was traced

The first read-only native run used the exact first diagnostic container,
SHA-256 `57a6713d24a6d689b097588c36d922667b90adbb57f85737d4c31b1bb7147091`.
No firmware instruction, operation count or recorder state was changed by the
observer. This verifies the candidate bytes, not the installed device hash.

The guard counts stock sample load/unload/clear calls, rather than FREEZE jobs.
In the emulator's existing card/project fixture, 1,915 operations completed:

| Operation | Entries | Caller return PC, OS 1.16 |
| --- | ---: | --- |
| Initial sample clears | 1,024 | `0x40154366` |
| Sample loads | 297 | `0x4004eaae` |
| Nested unloads | 297 | `0x4015461c` |
| Nested clears | 297 | `0x40154206` |

Every entry had a matching exit. Peak nesting was three, from load → unload →
clear. The count was zero when the CPU first reported UI readiness, remained
zero after opening Sketch and PLAY, and had no remaining active frame. Thus
this fixture does **not** reproduce the user's first post-boot refusal. Native
instruction counts and modeled card/DSP transfers do not establish physical
load duration. The user's current project/sample contents remain unknown.

[Original-byte trace summary](../out/runs/sketch-startup-operations-audit-20261023-01/cold-trace-summary.json),
[raw trace and startup report](../out/runs/sketch-startup-operations-native-20261023-01/report.json).

## Focused device diagnostic

[Firmware, hash and use notes](../out/runs/sketch-startup-operations-20261023-01/package/README.md).
The file is `EXPERIMENTAL_SKETCH_BUF_SAMPLE_DIAG_OS1.16.syx`, SHA-256
`419cbac7fc08f7ce9e60774110010fb09b336f16f45d035519c197a08c2790c9`.
The assistant has not transferred it to hardware.

Use the existing SONG / FUNC+SONG controls. Collect the first complete refusal
message after a fresh startup; no repeated-shortcut sequence is needed.

| Message | Meaning of the number |
| --- | --- |
| `BUSY LOAD n` | Sample-pool slot of a still-active outer stock load |
| `BUSY UNLOAD n` | Sample-pool slot of a still-active outer stock unload |
| `BUSY CLEAR n` | Sample-pool slot of a still-active outer stock clear |
| `BUSY SAMPLE n` | Operation count; outer context unknown or already returned |

The slot number is not BUF 1–4. The fallback does not attribute another
concurrent operation to an old outer frame. Existing WORKER, LOADER and other
admission labels remain. The failed request's snapshot stays visible even if
the operation finishes later; the message is not a live busy indicator.

The opt-in `operation_diagnostics` profile records the outer wrapper/caller,
arguments, task, raw tick, frame, return state and entry/exit totals. Metadata
is captured on the count's 0→1 transition. The outer return is matched by its
stack frame, so a nested return does not mark its parent finished. ARM reads
the metadata and original count together under an interrupt mask. Sketch
latches that snapshot before interpreting recognized wrapper addresses.
Unknown or returned outer contexts retain the generic sample-busy message.

No count is cleared, lease claimed, automatic retry scheduled, or recorder/
FREEZE job submitted by this diagnostic. Guard predicates, return ABI,
capture/publication/cancellation, FREEZE jobs, DSP, hooks, reservation and
memory policy remain. The diagnostic extends the masked counter update by a
small fixed instruction sequence; physical timing is unqualified.

The pending clock correction is excluded. The builder rejects combining its
profile with this diagnostic. The ordinary MAIN and first ARM-diagnostic MAIN
still match their original hashes; both old packages are preserved.

## Validation

- 167 BUF, 52 core and 30 integration unit tests pass. New controls cover
  nested counts, arguments, return/interrupt-mask restoration, atomic refusal
  snapshots, latched rendering and exact profile scope.
- Native full-container application startup passes. The instrumented counter
  records 1,915 entries and 1,915 exits, matching the independent read-only
  observer, with final count zero and the outer frame returned.
- Five injected native FUNC+SONG controls exercise load/unload/clear and
  returned/unknown fallbacks. Two existing injected WORKER/LOADER controls also
  pass. Counters show no admitted BUF transaction or recording. These controls
  test the diagnostic; they do not reproduce the hardware failure.
- Actual frames display `BUSY LOAD 42`, `BUSY UNLOAD 43`, `BUSY CLEAR 44` and
  `BUSY SAMPLE 1`. The tiny initial preview was misread; enlarged pixel-exact
  captures confirm the labels. No rendering change was needed.
- Native CPU upload/backpressure, independent boot-stream rules, package
  integrity/protected sections, canaries, source checks, Ruff and SINE replay
  pass. The packager rejects missing operation-UI and cold-trace evidence.
- Zero new recordings, hardware transfers, commits, dependency updates or
  upstream edits. Physical DSP ROM/SPI, memory/cache/DMA, recorder, timing and
  listening remain separate unverified layers.

[Enlarged native control screenshots](../out/runs/sketch-sample-diag-native-20261023-01/diagnostic-contact.png),
[native report](../out/runs/sketch-sample-diag-native-20261023-01/report.json),
[package manifest](../out/runs/sketch-startup-operations-20261023-01/package/manifest.json),
[audit](../out/runs/sketch-startup-operations-audit-20261023-01/verification.json).

Earlier failed unit runs are retained: one rejected the unaudited inline OR
opcode in the held clock experiment; another exposed stale Unicorn translated
blocks when replacing the fixture's already-executed IRQ. The fixture now
invalidates those blocks explicitly. A profile-scope assertion also needed to
include the deliberately renamed FREEZE→SAMPLE diagnostic string. No admission
failure expectation or operation guard was relaxed.

## Reproduction

Use fresh ignored directories and the configured launchers:

```sh
./labctl doctor
python3 scripts/build-sketch-device.py out/runs/YOUR-SAMPLE-BUILD \
  --arm-diagnostics --operation-diagnostics
python3 scripts/check-sketch-boot-upload.py out/runs/YOUR-SAMPLE-BUILD \
  out/runs/YOUR-SAMPLE-UPLOAD --native-upstream /absolute/path/to/digikit-at-38dfbe4
python3 scripts/check-native-sketch.py out/runs/YOUR-SAMPLE-NATIVE \
  --build out/runs/YOUR-SAMPLE-BUILD --upload-proof out/runs/YOUR-SAMPLE-UPLOAD \
  --boot-only --operation-trace --arm-diagnostics \
  --native-upstream /absolute/path/to/digikit-at-38dfbe4
python3 scripts/package-sketch-arm-diagnostic.py \
  out/runs/YOUR-SAMPLE-BUILD out/runs/YOUR-SAMPLE-UPLOAD out/runs/YOUR-SAMPLE-NATIVE \
  out/runs/sketch-experimental-20261023-01/package out/runs/YOUR-SAMPLE-PACKAGE
```
