# Sketch coupled application startup — Digitakt II OS 1.16

This is historical application-startup evidence. The later
[boot-stream/upload audit](SKETCH-BOOT-UPLOAD.md) found that `-09` still had
invalid FINAL ordering and an unaligned append. Keep its measured results at
the application layer; use a fresh current device build for reproductions.

This checks the corrected `sketch-device-build-20261023-09` MAIN and DSP together:
CPU reset, DSP execution from the loader's application entry, native control
replies, native sample loading from the emulated card, and normal panel input.
It uses no prepared CPU/DSP ready snapshot and performs no recordings.

**This does not execute the DSP boot ROM or its boot-upload handshake.** The
emulator starts the DSP from decoded loader memory. The earlier
[boot-workspace exclusion and actual MAIN depacker checks](SKETCH-DSP-BOOT-MEMORY.md)
remain separate requirements; this result cannot replace them or establish
physical startup, caches, aliases, DMA ownership or worst-case stack bounds.

## Runner and input boundaries

`scripts/check-sketch-cold-boot.py` authenticates the sealed build and uses a
read-only native DigiKit checkout at
`38dfbe4ae88263511eed95691c07fc07e17b6f26`, Rust 1.98.1, and its regenerated
firmware-free core. The generated-core fingerprint and every input are hashed
in the report. The lab's pinned DigiKit/Selache and known runtime remain intact.
This is an explicit validation adapter, not a dependency migration.
`DeviceBuild` is used only to authenticate input bytes and reproduce the sealed
CPU image; its prepared-state installer is never called.

`lab/native/sketch_cold_inputs.py` runs in that checkout's Python environment
to pack the loader memory and reset-only register state. It executes zero
instructions and imports no captured checkpoint. The explicit peripheral reset
values are the authenticated model from the earlier bounded DSP startup check.
The DSP begins at `0x1c1338`, executes its initialization and reaches its RTOS
idle task. Bank/stack, interrupt, timer and peripheral models are enabled;
unmodeled reads or native traps fail rather than being patched around.

`lab/native/sketch_cold_probe.rs` attaches that DSP through the native DSPI2 and
LP0 peer before the CPU's first instruction/control frame. SSI's 96 kHz request
source and the DSP budget of 666,667 instructions per frame are model inputs,
not physical clock measurements. Upstream's exact idle-loop acceleration is
enabled after DSP initialization; no stock function is entered through a direct
call and no instruction PC is changed to bypass startup.

The CPU constructor uses the authenticated stock OS1.16 container and card. In
the device arm, it receives the exact candidate MAIN before reset, with the
entire CPU extension reservation poisoned first. The actual reset loader must
copy all 45 segments, clear the declared BSS, erase its appended source and
preserve all 30 canaries. The ready path must have native DSP execution/replies,
finite SPORT output, and drained sample transfers. NO dismisses the stock
filesystem modal and SONG opens/renders Sketch. All added DSP code regions and
CPU code/canaries are checked after the flow.

The CPU container still carries the stock DSP section; the DSP application
receives the exact corrected blob independently. This tests their live runtime
interaction and initialization, not candidate SYX decoding or CPU-driven ROM
upload. No candidate SYX, physical media, device transfer or firmware publication
is involved.

The disconnected control disables the DSP peer while using the same CPU path.
Every mode must satisfy the same measured gate after eight CPU frames: native
DSP instructions and nonzero native replies must both exist. The disconnected
case must fail that gate. Its mode name alone is not a reason to fail.

## Reproduction

```sh
./labctl doctor
python3 scripts/check-sketch-cold-boot.py \
  out/runs/sketch-device-build-FRESH \
  out/runs/sketch-cold-boot-FRESH \
  --native-upstream "/absolute/path/to/clean/digikit-at-38dfbe4"
./labctl unit buf
./labctl test sine --replay
```

Use a fresh ignored run folder. The script selects the configured Python 3.12,
freezes sources, builds offline, bounds DSP initialization to 400 million
instructions, and bounds each CPU startup to two billion instructions and ten
minutes of wall time. It refuses source, generated-core or dependency drift.
Native input/CPU callbacks are observations and normal panel controls; no host
recording commit, generation publication, seal grant or retirement certificate
is used.

The initial run is retained at `out/runs/sketch-cold-boot-20261023-01/`.
It passed stock/device startup; its first disconnected control stopped based on
the configured mode at the first frame. The final run at
`out/runs/sketch-cold-boot-20261023-02/` tightens that
control to the common execution/reply counters above. The two changed validator
files are frozen in each run. The first SINE attempt is retained as a source-drift
failure because the validator was tightened during that replay; its firmware
and backend sources were unchanged. Final SINE validation uses frozen sources.

## Remaining qualification

Passing this application-startup check establishes live native CPU/DSP startup
under the stated models. Hardware readiness still requires the ROM/upload and
container boundary, physical memory/cache/DMA/stack qualification, and eventual
device testing. General machine compatibility, device-address obsolete-generation
retirement, physical recording/publication timing and listening are separate.

## Results — 2026-10-23 JST

The [final evidence index](../out/runs/sketch-cold-boot-20261023-02/verification.json)
passes with the exact corrected MAIN
`cfec08206f18de3ae235ebaad92f4bd9750ba2247a820dd71c576e0a3a1a986c`
and DSP `e5316478d6ac2544bb8eef7daac5256fe3e36122b2c1c96a52d2bb1fb9dfe13b`.

| Observation | Stock | Sketch/BUF |
| --- | ---: | ---: |
| DSP initialization instructions to stable RTOS idle | 238,750,000 | 238,750,000 |
| CPU ready instruction | 1,183,235,698 | 1,185,116,065 |
| Native DSPI2/SPORT frames through end of check | 6,110 | 6,879 |
| Nonzero native DSP replies | 6,107 | 6,876 |
| Native LP0 sample-transfer units | 1,620 | 1,620 |
| Missing SPORT blocks / queued LP0 bytes at end | 0 / 0 | 0 / 0 |

Counts are emulator observations, not device cycles or elapsed recording time.
The BUF check includes extra panel interaction after ready, so its frame total
is higher. Both positive reports repeat exactly between the two fresh runs,
apart from wall time. No saved ready state or new recording is used.

The BUF arm verifies all 45 reset segments, explicit BSS clearing over poisoned
RAM, source erasure, all 30 CPU canaries, CPU code/hooks and all three added
DSP code regions. Native NO/SONG input opens Sketch, which draws BUF 1 and four
empty buffers. The initial recorder length is MAX; no ARM/FREEZE job is tested
or submitted in this startup check.

The disconnected arm fails the shared gate after eight CPU frames with
`Native DSP coupling absent after 8 CPU frames`. This is the required negative,
not a failed firmware candidate. [Full startup/control report](../out/runs/sketch-cold-boot-20261023-02/report.json).
145 scoped BUF unit tests and focused Ruff pass. Final-source SINE passes at
`out/runs/20261023T022243Z-test-b9faf0f1/`; its full source manifest matches the
final startup run. Firmware emitters, backend algorithms, sealed images, prior
test helpers, dependencies and original SYX/card bytes remain exact. Only three
new validation files are added. The final runner binary and frozen sources are
retained with the report. No firmware, library, dependency or hardware repair
was needed for the positive startup checks.

![Native Sketch after coupled application startup](../out/runs/sketch-cold-boot-20261023-02/device/panel.png)
