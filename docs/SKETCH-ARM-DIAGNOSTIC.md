# Sketch ARM diagnostic package — OS 1.16

Follow-up: the user reports `BUSY FREEZE 1` first after power-on and PLAY, then
later `REF CLOCK 0`. Prioritize that first refusal. The separate
[startup sample diagnostic](SKETCH-STARTUP-SAMPLE-DIAGNOSTIC.md) identifies the
guarded stock operation without including the pending clock correction. This
document and its original package retain the earlier diagnostic evidence.

The user reports the first experimental firmware reaches the physical Digitakt
UI, but ARM returns REFUSED or BUSY, including after a power cycle. The Sketch
status row reads REC READY / BUF IDLE and pattern length is reported as 16/16.
These are user observations, not a verified device image hash or recording
result. Pattern mode/scale and the blocking condition remain unconfirmed.
The user authorized this diagnostic package during the voice session.

## Delivery and use

[Diagnostic firmware and notes](../out/runs/sketch-arm-diagnostic-20261023-01/package/README.md).
The file is `EXPERIMENTAL_SKETCH_BUF_ARM_DIAG_OS1.16.syx` with SHA-256
`57a6713d24a6d689b097588c36d922667b90adbb57f85737d4c31b1bb7147091`.
The assistant has not transferred this diagnostic package to hardware.

Use the same Sketch controls. After one FUNC+SONG attempt, read the entire
bottom message. A refused second attempt can replace the first message, so do
not repeatedly press the chord while collecting the result. The number is
the observed unsigned value at the first failed check.

| Label | Check that blocked this attempt |
| --- | --- |
| BUSY REQUEST | Existing BUF transaction phase |
| BUSY WORKER | Shared worker/mutation lease |
| BUSY FREEZE | Guarded native-operation count in the FREEZE worker state |
| BUSY LOCK | Generation mutation gate |
| BUSY LOADER | Stock sample-loader busy word |
| BUSY RECORDER | Stock recorder state |
| REF BUF / PLAY / CTRL | Invalid BUF argument, transport state or controller |
| REF LENGTH | Unsupported native recorder length |
| REF CLOCK | The normal bar-clock validity flag is not admitted |
| REF MODE | The measured clock-selector guard does not match; this alone does not classify external clock |
| REF SETUP / POOL / KIT | Buffer initialization or project context is unavailable |

This reports a failed predicate, not its underlying cause. It does not clear
busy flags, bypass admission checks or claim to repair physical recording.

## Implementation and validation

The diagnostic profile is opt-in. The ordinary profile still emits the exact
original MAIN, and the DSP stream is byte-exact in both profiles. Only four
existing relocated payloads change: explicit ARM admission, Sketch's ARM-result
snapshot, its feedback drawing and its text pointer table. Additional strings
are data only. Stock hooks, all arenas, guards, record/start/stop/worker/
publication/cancellation/FREEZE code and memory policy remain unchanged.

ARM still returns the same success/BUSY/REFUSED/LENGTH ABI. On failure it stores
the first branch's reason and the value used by that branch in two dedicated
words outside the admitted transaction state. Sketch snapshots those words
when the request returns, so later backend changes cannot relabel the message.
Successful admission clears the old diagnostic. Unknown reason IDs fall back
to the ordinary feedback path rather than indexing outside the table.

- 212 BUF/core and 30 integration tests pass. Four focused additions cover
  every refusal, first-failure priority, unchanged rejected transaction/worker
  state, successful admission equivalence, latched rendering and profile scope.
- Native startup passes from the full candidate CPU container and independent
  DSP application entry. Actual DSP ROM/physical SPI remain outside the model.
- Two test-only injected busy words are exercised through native FUNC+SONG.
  They render `BUSY WORKER 66` and `BUSY LOADER 1`; admission/capture counters
  remain unchanged and the labels retain their values after the injected flags
  are restored. These examples are not the user's device diagnosis.
- Native CPU upload/backpressure, independent boot-stream rules, final package
  checksums/seal, protected sections and staging bounds pass. The packager
  refuses a missing native diagnostic proof and a mismatched startup container.
- SINE replay and focused Ruff/format checks pass. No recording or stress
  experiment is repeated.

[Worker screenshot](../out/runs/sketch-arm-diag-startup-20261023-01/diagnostic-worker.png),
[loader screenshot](../out/runs/sketch-arm-diag-startup-20261023-01/diagnostic-loader.png),
[package manifest](../out/runs/sketch-arm-diagnostic-20261023-01/package/manifest.json).

The first guard-matrix test left one of the two transport flags set; it was
corrected to exercise stopped transport. That failed log and the intermediate
pre-lint build remain intact. No failure expectation or recording guard was
relaxed. The original experimental package remains untouched.

## Reproduction

Use fresh ignored directories and configured Python through the launchers:

```sh
./labctl doctor
python3 scripts/build-sketch-device.py out/runs/YOUR-DIAG-BUILD --arm-diagnostics
python3 scripts/check-sketch-boot-upload.py out/runs/YOUR-DIAG-BUILD out/runs/YOUR-DIAG-UPLOAD \
  --native-upstream "/absolute/path/to/clean/digikit-at-38dfbe4"
python3 scripts/check-native-sketch.py out/runs/YOUR-DIAG-STARTUP \
  --build out/runs/YOUR-DIAG-BUILD --upload-proof out/runs/YOUR-DIAG-UPLOAD \
  --boot-only --arm-diagnostics --native-upstream "/absolute/path/to/clean/digikit-at-38dfbe4"
python3 scripts/package-sketch-arm-diagnostic.py \
  out/runs/YOUR-DIAG-BUILD out/runs/YOUR-DIAG-UPLOAD out/runs/YOUR-DIAG-STARTUP \
  out/runs/sketch-experimental-20261023-01/package out/runs/YOUR-DIAG-PACKAGE
```

All earlier physical ROM, memory/cache/DMA/stack, recorder/normalization,
timing, persistence and playback limitations remain. The next useful evidence
is the exact diagnostic message from the device.
