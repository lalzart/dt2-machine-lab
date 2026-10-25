# Optional STRETCH CAPI comparison — OS 1.16

2026-10-13. Local implementation; physical device testing remains separate.

The optional build exposes CAPI on encoder C of the existing STRETCH machine.
The default is OFF. OFF selects the original renderer; ON uses the preserved R3
Capicola renderer when its selected mono bank is ready. Changes apply on the next
native trigger, including parameter-lock values. There is no new machine ID.
The original TUNE, PLAY, sample, trim, BARS and level controls remain in place.

The second SRC page (the waveform page) reports the last received DSP state: WAIT, READY, CAPI, STOCK, MIX or
UNSUP. Active engine state takes precedence over a pending control change. Idle
OFF displays OFF; missing/expired feedback displays `?` when ON. Sixteen tracks
share one round-robin feedback halfword, with a bounded 32-byte CPU cache. This is
buffered status information, not a physical latency measurement.

Preparation and bank storage are the existing R3 implementation. OFF still lets
background preparation run so a later ON trigger can use the prepared bank. The
8 MiB reservation and 12-second per-source limit remain unchanged. Only one
engine renders a lane at a time; this toggle does not run both audio engines for
an A/B blend.

The code is isolated in `lab/capicola_toggle.py` and
`machines/plaits-capicola-stretch-toggle/machine.c`. The firmware stores new CPU helpers after `0x40320000`; its native reset copy
initializes them into the unused internal SRAM tail at `0x8000f180`, below
`0x80010000`. The existing external clear still runs. This uses about 1 KiB of
SRAM and preserves previous Flex/Plaits allocations and all old initialized
SRAM bytes. Both decoded CPU code spans have zero static references to the tail;
computed references and physical ownership remain separate limitations. All patch sites and the complete CPU baseline are hash/byte guarded.
The default builder omits this layer and asserts the existing MAIN, DSP and SYX
hashes exactly. New firmware and captures stay in ignored `out/runs/` directories.

## Reproduction

Use the configured Python 3.12 environment (the scripts select it automatically).
Choose fresh output directories. Build with:

```sh
python3 scripts/build-combined-firmware.py out/runs/<package> \
  --capi-toggle --elekloader-reference out/references/elekloader-upload-audit
python3 scripts/check-capicola-toggle-cpu.py out/runs/<cpu-check> \
  --package out/runs/<package>
python3 scripts/check-capicola-toggle-native.py out/runs/<dsp-check> \
  --package out/runs/<package>
python3 scripts/capture-capicola-toggle.py out/runs/<panel-check> \
  --package out/runs/<package> --replies out/runs/<dsp-check>
```

Omit `--capi-toggle` to reproduce the prior combined firmware.

## Validation corrections

Failed runs are retained. Smoke builds corrected the MAIN end address, actual
SPI2 driver target and new `AUTO.slices` relocation literal using the inspected
1.16 image and generated assembly. The first panel run caught a string-setter ABI
error: the native function requires a string reference, not the character
pointer. The corrected wrapper retains the immutable string representation and
passes both native CPU and panel tests without faults. The first cold-start run
then proved that external RAM from `0x40312000` through `0x47e28470` is deliberately
cleared, including the initial append placement. Revision 2 extends the guarded
second SRAM-copy source end and links the helpers to the internal SRAM tail;
original copy data and both clear bounds are unchanged.

The playback comparator now observes native trigger scheduling across adjacent
blocks. Status comparisons use native active flags: a completed finite note
reports READY rather than CAPI even though its lane remembers the previous
backend. Neither correction changes renderer tolerances.

OFF sample rendering must match stock exactly. The fresh initial OFF phase also
has exact stock master/DAC-ring output. After a Capicola passage, downstream
filter/effect history differs from an instrument that has only played stock;
therefore returning to OFF is compared at the sample-renderer boundary. The
builder does not reset effects when changing the engine.

## Remaining device boundaries

Local CPU/DSP emulation cannot establish physical timing, spare DSP headroom,
permanent code/memory ownership or coupled processor operation. Full project
storage/undo and continuous live DSP-to-CPU feedback are separate from native
parameter storage, lock recall and buffered replies. Existing R3 playhead/progress
bookkeeping and Flex source-lifecycle gaps remain. No firmware has been flashed
or sent to a connected device as part of this implementation.

## Final artifact and verified results

Final local classification: **local-experimental-validated**, with physical
hardware and timing unverified. Canonical package:
`out/runs/capi-toggle-final-01/EXPERIMENTAL_PLAITS_R3_FLEX_CAPI_TOGGLE_OS1.16.syx`.
The package also retains Plaits R3 and managed streaming Flex.

| Item | Exact value |
|---|---|
| SYX SHA-256 | `e544a918baf477847c19284370eca8e9a4f60c81a450dc22e1dfb2640681b1aa` |
| MAIN SHA-256 | `7f911a1e68158f991f9327d8cfae10a143824959f319b930eb4f3e40a9cba989` |
| DSP SHA-256 | `cee93f5173313dabba145c9c0869f4133a700d1f09d8657305c1f3f593faf8d7` |
| Added MAIN bytes | 1,172, including 160-byte alignment gap |
| Live SRAM payload | 1,012 bytes, `[0x8000f180,0x8000f574)` |
| New SRAM-copy source end | `0x403203f4` |
| DSP code extent | 91,884 bytes, including two zero padding bytes |

| Check | Retained result |
|---|---|
| Source tests | 144 pass; `capi-toggle-final-01/source-tests.log` |
| Native CPU | `capi-toggle-sram-cpu-01/report.json`; 65,536 formatter cases, native range checks, 153 permissions, 4,536 reverse mappings, 128 late repacks, 560 caption cases, RX arguments/results/CCR and stale-status clearing pass |
| Native panel, locks and feedback | `capi-toggle-sram-panel-01/report.json`; real encoder C, native stored ON base/OFF step lock, original SPI2 receive path and all six native status enums pass; immutable SRAM payload retained and zero CPU fault pages |
| Fresh DSP playback | `capi-toggle-final-native-01/report.json`; OFF stock PCM exact, ON R3 maximum error zero, sixteen distinct/mixed tracks, retrigger latching, unsupported fallback, idle and explicit MIX states, and 56 other-machine blocks pass |
| Initial DSP load | `capi-toggle-final-load-01/report.json`; all code/constants/selector bytes match before startup |
| Separate startup | `capi-toggle-final-startup-01/report.json`; CPU 400M checkpoint, nine tasks and 127 immutable writes retained; two DSP 500M runs retain code/constants/selector and repeat exactly |
| Original bootstrap depacker | `capi-toggle-final-01/device-depacker.json`; sections 8, 3 and 7 match exactly |
| Required SINE regression | `20261013T031647Z-test-1a777bca/manifest.json`; pass |
| Omitted option | `capi-toggle-final-omitted-01/manifest.json`; original MAIN/DSP/SYX hashes exact, including SYX `cb57ee53d106b3bf05e3562d74e8d8f45889112da55043a1fb46976552a60229` |
| Formatting and diff | Ruff and `git diff --check` pass |

`capi-toggle-final-01/validation.json` joins the exact artifact identities. The
final MAIN is byte-identical to the passed SRAM CPU/panel input. The final DSP's
691 reply snapshots are byte-identical to the replies used in that panel replay.
Source hashes still match the final build. The two-byte DSP padding corrects
native packing of the final partial word; the preserved engine source and every
assembled instruction byte remain unchanged. The previous unaligned run failed
retention at just one byte (`0x200966e8`), with constants and selector intact.
Failed builds, initial external placement and unaligned DSP runs remain saved.

Native CPU startup uses its existing modeled DSP boot peer. Native DSP startup
uses explicit reset-value peripheral models. The panel starts from a prepared
checkpoint and receives buffered native replies. These are separate checks,
not a coupled hardware run or a complete project storage/undo test. Changes remain
uncommitted on `codex/plaits-macro-controls`.

## User hardware listening observation — 2026-10-13

**EVIDENCE (user report):** The user tested on hardware and reports that the two
settings sound nearly identical, with no discernible difference. The user then
confirmed that the waveform page showed `STRETCH CAPI` during the ON pass. This
is a reported backend indication and a listening result, not a captured hardware
audio trace.

**UNRESOLVED:** OFF-pass `STRETCH STOCK` indication, sample format and full
length, amount of pitch/time change, and whether each toggle change was followed
by a new trigger. Current source deliberately keeps the
backend latched during a note and falls back to stock for unready/ineligible
sources, including stereo or full samples longer than twelve seconds. We must
rule out an unchanged active note before attributing the listening observation
to the Capicola algorithm. No audible-improvement claim is established by the
existing emulator comparisons. The confirmed CAPI indication makes simple
ON-pass stock fallback a less likely explanation.

## Final-output audit — 2026-10-13

The earlier toggle validator compared renderer buffers and tested final output
only during the initial OFF phase. Its negative comparison established buffer
inequality, without measuring the ON-versus-OFF final mix. This was insufficient
to explain the hardware listening report.

Added `scripts/check-capicola-toggle-output.py`. It uses the exact final-package
DSP (`cee93f5173313dabba145c9c0869f4133a700d1f09d8657305c1f3f593faf8d7`),
the hash-checked control/LP0 fixtures, and an explicit generated one-second mono
percussion-plus-tone sample. Three instances start from the same prepared native
checkpoint: OFF, ON, and ON with only the prepared bank's amplitude values
zeroed. Original PCM, keyframe times, generations and compiled code are preserved
in this causal negative control. All instances run the native frame handler.

**EVIDENCE:** `capi-listening-audit-03/report.json` passed four one-second
final-master comparisons. Each used 1,500 native blocks per instance. Both
engines received exactly the same native pitch/advance inputs; OFF lanes were
stock and ON lanes were custom. The muted custom bank produced exact silence
at the final master in every case.

| Tune | BARS wire raw | Native pitch | Native advance | Stock RMS | CAPI RMS | Difference RMS |
|---|---:|---:|---:|---:|---:|---:|
| 0 | 0 | 1 | 0.425 | 0.044445 | 0.045076 | 0.063571 |
| +12 | 0 | 2 | 0.425 | 0.048269 | 0.043001 | 0.062625 |
| -12 | 0 | 0.5 | 0.425 | 0.042878 | 0.041374 | 0.052220 |
| +12 | 768 | 2 | 0.053125 | 0.029346 | 0.033829 | 0.044915 |

RMS values use normalized float amplitude. Waveform difference can include phase
and splice timing; it is not an audibility threshold or a quality score. The
audit-03 `trace_off_vs_on` fields compare different processing stages and must
not be used as an engine-quality comparison. Its one-second WAVs are final-master
taps at native gain, not physical-device recordings.

**EVIDENCE:** The maintained script passed under
`capi-listening-audit-04/report.json`: four cases of 96 blocks per instance,
1,152 native blocks total. Every block's final master converted to the actual
DAC-facing ring exactly (maximum Q31 error zero). OFF/ON ring signals differed,
and the custom-bank mute silenced the ring in all four cases. This establishes
causal routing in the emulator. Source hashes stayed fixed; all 144 source tests,
Ruff and `git diff --check` passed. No DSP algorithm or firmware bytes were
changed for this audit.

Reproduce the checked short run with a fresh output directory:

```sh
./scripts/check-capicola-toggle-output.py out/runs/<unique> \
  --package out/runs/capi-toggle-final-01 \
  --checkpoint out/runs/capi-listening-audit-02/prepared-checkpoint.pack \
  --blocks 96
```

The checkpoint's source identities and original PCM are checked. Omitting
`--checkpoint` prepares a new bank; omitting `--blocks` selects 1,500 blocks per
case. Bank preparation in the retained checkpoint took 3,003 native blocks.
The first probe had too short a preparation bound, and the second could not
resume a diagnostic PC breakpoint. Those interrupted attempts and their inputs
remain saved; the final check uses bank-amplitude mutation instead.

**UNRESOLVED:** The user's actual sample/settings and OFF-pass backend. The
model shows that CAPI reaches final output; the hardware listening observation
still establishes no discernible improvement. Reproduce that specific A/B
before changing the algorithm or attributing the result to a particular feature.
