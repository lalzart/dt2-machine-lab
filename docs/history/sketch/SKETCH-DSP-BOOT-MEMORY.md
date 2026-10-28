# Sketch DSP boot-memory correction — OS 1.16

This records the placement correction. A subsequent
[boot-stream/upload audit](SKETCH-BOOT-UPLOAD.md) found additional FINAL,
alignment and FIRST-span defects in `-09`; the current device recipe fixes
those too. The results below remain scoped to their original image hashes.

The device-preparation audit found a concrete boot conflict in the earlier
prepared-emulator DSP layout. Its retirement-gate zero-fill block covers
`0x200fc000..0x20100000`, including all 8 KiB of the ADSP-2156x boot kernel's
workspace at `0x200fe000..0x20100000`. ADI states that this workspace remains
reserved until boot completes and that violating it can raise a boot exception.
See [ADI's support explanation and exact boundaries](https://ez.analog.com/dsp/sharc-processors/adsp-2156x/f/q-a/566931/secure-booting---using-secure-boot_open-part-directory)
and the [public hardware reference](https://www.analog.com/media/en/dsp-documentation/processor-manuals/adsp-2156x_hwr.pdf).
Zero-fill blocks are writes, even though they take little space in the stream.
Prepared snapshots and flattened loader images bypass this ROM ownership issue.

The former build `out/runs/sketch-device-build-20261023-07/` is preserved as
emulator evidence and is unsuitable for hardware packaging. Its earlier CPU
reset and prepared coupled results remain evidence for those specific layers;
they did not execute the DSP boot ROM.

## Focused correction

Only the opt-in device recipe moves the 16 KiB retirement-gate state to
`0x200e8000..0x200ec000`. The existing source is recompiled with that address;
its wrapper scratch, stacks, data anchor and native seal consumer use the same
placement. There is no binary-wide address replacement. The loader fills the
new state deterministically, and no block writes the boot workspace.

`lab/sketch_dsp_device.py` checks decoded destination extents, including fill
blocks, before accepting a device build. The native builder accepts an optional
gate-state placement; the ordinary emulator build keeps its original layout,
bytes and metadata. Neither historical contract constants nor BUF/FREEZE
algorithms, CPU placement, allocation policy, identities or feature profiles
are changed. The new candidate has the same DSP stream and state sizes.

The new build is `out/runs/sketch-device-build-20261023-09/`:

| Image | SHA-256 |
| --- | --- |
| MAIN, unchanged | `cfec08206f18de3ae235ebaad92f4bd9750ba2247a820dd71c576e0a3a1a986c` |
| Device DSP, 339,070 bytes | `e5316478d6ac2544bb8eef7daac5256fe3e36122b2c1c96a52d2bb1fb9dfe13b` |
| Ordinary emulator DSP, unchanged | `db737142a31e6e393de5c802dc0a94396d2e0a9e2a3fd625a0fb242efb943ff7` |

## Validation

The evidence index is `out/runs/sketch-memory-startup-20261023-01/`.
These checks perform **zero new recordings**.

- The previous fill destination is rejected. Partial overlaps from either
  boundary also refuse. A fresh ordinary DSP rebuild and its metadata match
  the previous build exactly; MAIN is byte-identical as well.
- A bounded native DSP application-entry comparison starts from loader bytes
  at `0x1c1338`, without a prepared snapshot or skipped instructions. The same
  existing public-register reset-value model is used for stock and candidate.
  Both execute 250,000,000 instructions without a halt and end at `0xb863bd`
  with identical exported state hashes. All six added code/state regions stay
  byte-exact, including the relocated gate state. This is a bounded startup
  observation, not paired CPU/SHARC cold boot or ROM execution.
- Fifteen existing native DSP admission/seal controls pass against saved sample
  pages and the new image. They include valid private-owner sealing, exact retry,
  retained/active readers, pending selection, logical/snapshot/preview roots,
  unknown extents, wrong-token refusal, enabled/disabled SEC and a destructive
  pending-descriptor comparator that changes PCM. These are prepared ABI/SEC
  fixtures, not a new coupled recording or general host retirement permission.
- Twenty-four native SPI/SEC blocks using saved B/current and A/frozen pages
  produce identical replies and finite, nonzero voice PCM between the old and
  new DSP images. This is a prepared old/new comparison; the earlier stock-file
  oracle is retained, not rerun or relabeled as a new coupled result.
- The actual unchanged OS1.16 MAIN depacker reproduces the new 339,070-byte
  DSP stream exactly from 210,649 compressed bytes. Its real 1 MiB allocation,
  command byte and end canary stay intact; decoded output plus command leaves
  709,505 bytes of headroom. Oversize input/output controls refuse. MAIN matches
  its earlier bootstrap-depack evidence byte-for-byte, so that check is reused.
- 227 scoped BUF/core/integration unit checks pass. The scope is the affected
  shared builders and BUF; unrelated machine suites are not selected.
  Focused Ruff and final-source SINE replay pass. SINE evidence is
  `out/runs/20261023T015816Z-test-7e802725/manifest.json`.

The [evidence index](../../../out/runs/sketch-memory-startup-20261023-01/verification.json)
links the [startup comparison](../../../out/runs/sketch-dsp-startup-20261023-01/report.json),
[native seal controls](../../../out/runs/sketch-device-seal-20261023-01/report.json),
[voice parity](../../../out/runs/sketch-memory-startup-20261023-01/voice-parity.json),
[staging check](../../../out/runs/sketch-memory-startup-20261023-01/streams.json)
and [default-build compatibility](../../../out/runs/sketch-memory-startup-20261023-01/compatibility.json).
Ignored reproduction helpers are retained alongside the reports. Only six
executable source files change or are added relative to this turn's initial
source snapshot; all other inherited executable files remain exact. The two
affected test helpers are separately hashed and copied into the evidence folder.

Reproduce with fresh output directories and the configured Python 3.12:

```sh
./labctl doctor
./labctl unit buf core integration
python3 scripts/build-sketch-device.py out/runs/sketch-device-build-FRESH
python3 scripts/check-sketch-dsp-startup.py \
  out/runs/sketch-device-build-FRESH out/runs/sketch-dsp-startup-FRESH
"$LAB_PYTHON" scripts/with-type7a-runtime.py \
  out/runs/sharc-type7a-build-20261022-02 -- \
  tests/native_recorder_seal.py out/runs/sketch-device-seal-FRESH \
  --fixture out/runs/recorder-native-retirement-smoke-20261022-02 \
  --build out/runs/sketch-device-build-FRESH/dsp
./labctl test sine --replay
```

Set `LAB_PYTHON` to `.local/config.json`'s configured interpreter. Build and
startup scripts re-execute under it automatically; the standalone native seal
fixture needs it explicitly. The earlier build and intermediate build `-08`
are retained; `-09` contains the final source manifest for this correction.

## Remaining qualification

Subsequent [coupled application startup](../../SKETCH-COLD-STARTUP.md) passes CPU reset
and live DSP initialization/control/sample loading with the corrected image.
It does not execute the DSP ROM or boot-upload handshake; those boundaries and
physical ownership remain unqualified. The earlier milestone's scope follows.

Removing a documented boot collision does not establish exclusive runtime
ownership of the lower L2 interval, physical cache/alias/DMA behavior, worst-case
stacks or load pressure. The inspected separate upstream has a coupled cold-boot
path, but its ready-input pipeline and core have not been adopted into this
lab's pinned OS1.16 runtime. Paired CPU/SHARC cold initialization remains next.

The current MAIN has earlier CPU-reset evidence; the new DSP has the bounded
entry and prepared seal evidence above. A device-address coupled flow with
actual obsolete-generation retirement remains separate, as do real-time
publication latency, listening and hardware. No SYX, hardware transfer, commit
or publication was made.
