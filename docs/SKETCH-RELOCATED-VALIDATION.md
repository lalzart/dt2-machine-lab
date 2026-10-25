# Sketch/BUF validation at device addresses — OS 1.16

This records the exact original `-07` prepared-emulator result. Subsequent
[DSP boot-memory auditing](SKETCH-DSP-BOOT-MEMORY.md) found a boot-workspace
overlap in that image. Its emulator results remain valid at the stated layer;
the corrected `-09` DSP has separate startup/seal evidence and no new recordings.

Continue the [device placement experiment](SKETCH-DEVICE-PLACEMENT.md) using
its exact sealed MAIN and DSP, without changing firmware emitters, the memory
layout, allocator policy or existing Flex builds.

The bounded check uses `scripts/check-sketch-dsp.py --device-build <build>`.
`lab/sketch_device_validation.py` authenticates the saved build, compares the
current CPU emitters with its exact MAIN/metadata, reads and verifies the sealed
segment chain, and installs those initialized segments into a prepared stock
CPU. The normal native hooks execute at `0x47e9b000..0x47ef3000`.

This is a prepared-boundary installation, separate from the earlier native
reset-loader check. It does not constitute paired CPU/SHARC cold startup or a
device installation. Recorder input, SSI cadence, LP0 delivery and SEC reset
contents retain their explicit models.

The adapter attaches only the existing recorder peer and read-only observations
to the device profile. It never runs the earlier synthetic-address installer,
host capture commit, resource resolver, sample loader or assignment operation.
The old CPU arena range is guarded against native reads, writes and execution.
Observation symbol views leave emitter globals and emitted bytes unchanged.
All 30 canaries and all classified code/hook bytes are checked after the flow.

The acceptance sequence is two captures with one FREEZE: initialize empty BUF 1
through native ARM and cancel before START; select it normally on T1/T5; play
the native pattern; record A; hold SONG to freeze A; select the snapshot on T6;
record B into the shared BUF. Require immutable A/snapshot identity, stable
assignments, native queued completion, correct LP0 PCM, retained old voice
pointers, finite/nonzero B and frozen-A voice output, no old arena accesses,
and intact code/canaries. Capture/publication latency remains a model result.

The `--setup-only` option stops before the first recording and uses modeled
control replies to make a short setup gate. It qualifies neither coupled voice
execution nor recording. The normal run uses the same native SPI/SEC DSP
engine and stock-file PCM comparators as [combined validation](SKETCH-VALIDATION.md).
Saved pages can be replayed without recording again.

```sh
./labctl doctor
./labctl unit buf
"$LAB_PYTHON" -B scripts/check-sketch-dsp.py out/runs/device-setup-FRESH \
  --device-build out/runs/sketch-device-build-20261023-07 --setup-only
"$LAB_PYTHON" -B scripts/check-sketch-dsp.py out/runs/device-coupled-FRESH \
  --device-build out/runs/sketch-device-build-20261023-07
"$LAB_PYTHON" -B scripts/check-sketch-dsp.py out/runs/device-audio-FRESH \
  --replay out/runs/device-coupled-FRESH
```

Set `LAB_PYTHON` to the configured Python 3.12 interpreter in `.local/config.json`.
Use fresh ignored output directories. The existing build remains immutable;
its source hashes must remain exact except for the deliberately extended
validation script, and the current CPU builder must reproduce its MAIN exactly.
New validator sources and each run's provenance are recorded separately.

Hardware memory/alias/cache/DMA/stack ownership, physical timing and I/O,
paired cold startup, other machines and shared-hook feature composition remain
separate gates. No SYX, hardware transfer, commit or publication is part of
this validation.

## Results — 2026-10-23 JST

`out/runs/sketch-relocated-validation-20261023-01/` is the evidence index.
CPU-only setup passes with zero captures; the coupled run performs exactly two
captures and one held-SONG FREEZE, passing 23 checks over 34,249 native DSP blocks.
The device MAIN remains
`cfec08206f18de3ae235ebaad92f4bd9750ba2247a820dd71c576e0a3a1a986c` and the DSP
remains `db737142a31e6e393de5c802dc0a94396d2e0a9e2a3fd625a0fb242efb943ff7`.

- Empty BUF 1 initializes and is selectable before recording. T1/T5 remain on
  slot 300, T6 is deliberately selected onto frozen slot 312, and every capture
  and FREEZE preserves the existing assignments. Recorder DEST remains NORMAL.
- A contains 112,960 stereo frames, token `0x7ffb0001`; B contains 112,928 frames,
  token `0x7ffb0002`. Native LP0 PCM matches the modeled recorder input exactly.
  FREEZE completes through the native queued worker and preserves A's snapshot
  descriptor across B publication. Current B and frozen A both produce finite,
  nonzero native voice PCM after B publishes.
- Four active old lanes (0, 1, 8, 9) retain their pointers across B publication.
  This does not qualify general obsolete-generation retirement at the relocated
  addresses: frozen A and current B remain rooted throughout this two-take flow.
- All 30 canaries and all classified native code/hook bytes remain exact.
  There are zero native old-arena accesses and zero CPU fault pages. The earlier
  synthetic-address installer is never invoked in the device-mode fixture.
- Both PCM takes, both full LP0 page histories, the final wire frame and the
  complete live voice-stream hash exactly match the previous accepted layout.
  These are comparisons of saved results; no baseline recording was repeated.
- Fresh stock CPU file loads and stock SHARC voice PCM match exactly for
  A/current+frozen (12 blocks), retained A across B publication (12), current B
  with frozen A (48), and late frozen A (24). The full 96-block scenario repeats
  exactly from fresh state. Deliberately substituting frozen B changes output.
  This replay performs zero recordings and does not clone live SEC state.

| Take | Capture to publication, modeled | First following T1 trigger | Publication frame |
| --- | ---: | ---: | ---: |
| A | 197.333 ms | 18,450 | 18,710 |
| B | 196.000 ms | 32,475 | 32,732 |

The timing and first-trigger relationship are unchanged. This placement step
does not make publication available on the following downbeat or establish
physical-device latency.

144 scoped BUF tests and focused Ruff pass. Final-source SINE passes at
`out/runs/20261023T012116Z-test-e787a5d3/`. Firmware emitters, DSP source, device
builder, target binaries and dependencies remain unchanged; only the validation
script is extended, a validation-only adapter is added, and two targeted unit
checks cover segment integrity and nonmutating observation symbols.

The first setup invocation used system Python and was refused before runtime
initialization. Its empty output directory/log is retained. The configured
Python 3.12 setup then passed; neither setup attempt consumed a capture.

See the [coupled report](../out/runs/sketch-relocated-coupled-20261023-01/report.json),
[stock-file PCM report](../out/runs/sketch-relocated-audio-20261023-01/report.json),
[prior-layout byte comparison](../out/runs/sketch-relocated-validation-20261023-01/prior-layout-parity.json)
and [native screenshot gallery](../out/runs/sketch-relocated-validation-20261023-01/screenshots.html).

The next preparation work is paired CPU/SHARC cold startup and SHARC/device
memory ownership qualification. No further recording is needed to repeat the
saved-page PCM comparator. This result does not clear those startup/physical
gates or qualify relocated obsolete-generation retirement.
