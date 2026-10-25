# Sketch clock correction candidate — OS 1.16

**Device follow-up:** after manually updating this candidate, the user reports
"it works now." The previously refused recording workflow therefore has a
positive user-reported device result. Which individual correction resolved it,
the installed-image hash and physical timing were not independently measured.
The next [selector/startup investigation](BUF-SELECTOR-AND-STARTUP.md) preserves
this working package. The candidate-stage limits below are the earlier evidence.

The user reports that the advancing `BUSY LOAD 259/261/262` refusal clears
after waiting for project samples to load. With playback still running, ARM
then reaches `REF CLOCK 0`. The loading block is transient in that device
report. `REF CLOCK 0` is the BUF bar-clock validity flag failing admission;
the exact physical prerequisite behind it has not been identified.

[Experimental clock candidate and use notes](../out/runs/sketch-clock-experimental-20261023-01/package/README.md).
File: `EXPERIMENTAL_SKETCH_BUF_CLOCK_OS1.16.syx`, 2,235,808 bytes, SHA-256
`7fcf8653b0aeb81204b7d0bc3b10d1419dac90f677fc097dfe11d5165988693d`.
The assistant has not transferred it to hardware. This is a correction
candidate with emulator evidence, not confirmed physical recording.

## Correction and boundaries

Two verified software checks can produce this refusal with supported setups:

| Before | Clock profile |
| --- | --- |
| IRQ requires both transport flags individually equal one, while ARM/CHECK use stock PLAY_GET | All three use the stock OR predicate, requiring its return value one |
| IRQ and CHECK compare twelve pattern bytes against one emulator fixture | Both check master length 16, normal mode 0 and qualified scale 2 |

The semantic fields are consumed by authenticated OS 1.16 start/source44 code:
master length at pattern `+0x1db74`, mode at `+0x1db79`, scale at `+0x1db7a`.
Other pattern fields no longer have to equal that fixture. Real contiguous
step progression still governs qualification; jumps or pattern replacement
re-prime the clock and invalidate pending context. A complete 15→0 followed
by 0→1 supplies each bar receipt. Unsupported lengths/modes/scales, the
separate clock-selector guard, stopped transport, missing/late receipts,
context/setting changes and the ten-second take cap remain guarded.

Additional clock refusals read `CLK NOIRQ`, `STOP`, `PATTERN`, `LEN`,
`PATMODE`, `SCALE`, `STEP` or `SERIAL`, plus the observed value. `NOIRQ 0`
means no enabled clock callback has yet supplied a failed prerequisite; it
does not independently establish the interrupt-controller cause. Existing
`REF MODE` reports the separate selector getter and does not classify external
clock by itself. Refusals latch their observed result.

An idle Sketch view now shows `WAIT SAMPLES` while either the shared sample
operation count or stock loader flag is busy. It clears when those guards
clear and preserves existing action/error feedback. A refused ARM at the
sample guard is named `BUSY SAMPLE n` in this profile. Loading still uses
shared sample memory; no guard bypass, deferred ARM or automatic retry was
added. A deferred request could remove the need to press ARM later, but
actual capture would still need to wait for safe admission.

After boot, open Sketch and let `WAIT SAMPLES` disappear before the first
ARM attempt. Use normal pattern mode, sixteen pattern steps, qualified 1×
scale, and Sketch recorder LEN 16/32/64. Start playback and press FUNC+SONG
once. A remaining refusal should now name a specific clock prerequisite.

The profile is opt-in (`--arm-diagnostics --clock-fix`). It remains separate
from the sample-operation tracing profile. Original/default MAIN, first ARM
diagnostic MAIN, sample diagnostic MAIN and the DSP blob retain their exact
previous hashes. Hooks, reservation, guards, recording/publication/FREEZE/
cancellation services and memory policy remain unchanged; IRQ qualification,
CHECK qualification, diagnostic admission/UI feedback and strings differ.

## Validation

- 251 scoped BUF/core/integration unit tests pass. The clock profile covers
  both single-flag stock playing states, changes to other pattern bytes,
  unsupported length/mode/scale, missing clock, jumps, duration, late/missed
  receipts and cancellation. UI checks cover each label and passive waiting
  without jobs or hidden errors.
- Exact container CPU application startup passes with an independently
  initialized DSP application entry. Code/canaries remain intact. Native
  injected controls show passive `WAIT SAMPLES`, its return to the idle hint,
  and unchanged WORKER/LOADER refusal behavior.
- The focused native recorder flow observes 25 actual step transitions and
  two real bar receipts, with no host writes supplying positive clock state.
  One test-only scale byte is changed and restored: the real IRQ rejects it,
  native FUNC+SONG displays `CLK SCALE 1`, and no capture is admitted.
- After recovery, one ARM cancels before recording. A fresh ARM starts at the
  next bar, stops after one bar and publishes 112,928 stereo frames. The PCM
  equals the deterministic modeled source. All sixteen assignments and
  NORMAL recorder DEST remain unchanged; post-capture code/canaries and DSP
  transfer integrity pass. This is modeled input/normalization, not physical
  ADC, listening, voice-retention or general clock qualification.
- Independent builds and container assembly match exactly. Native CPU
  upload/backpressure, stream/staging rules, protected sections and package
  integrity pass. The packager requires the matching clock flow and rejects
  missing clock evidence, host-supplied positive clock state and missing
  sample-wait UI evidence.
- Ruff and same-firmware SINE replay pass. After the final harness-only fix,
  the sole SINE inventory difference is `lab/native/buf_recording_probe.rs`,
  which SINE does not execute. The firmware/DSP and every other source hash
  remain exact; the passed replay is reused rather than repeated.

The first flow actually captured and published the same 112,928-frame PCM,
then its final validator treated the absolute `w.DEST` symbol as a relative
STATE offset and failed. That report stays failed. The corrected read and
shorter test-only ARM setup are in a fresh successful flow; firmware bytes
did not change. Two total modeled captures were performed across those runs.
The initial UI unit failure also used a relative test getter for an absolute
guard address; its corrected assertions retain the original expectations.

[Screenshots](../out/runs/sketch-clock-resume-audit-20261023-01/screenshots.png),
[native clock/recording report](../out/runs/sketch-clock-recording-20261023-02/report.json),
[startup report](../out/runs/sketch-clock-startup-20261023-02/report.json),
[package manifest](../out/runs/sketch-clock-experimental-20261023-01/package/manifest.json),
[audit](../out/runs/sketch-clock-resume-audit-20261023-01/verification.json).

Physical clock qualification, DSP ROM/SPI, input/normalization, cache/DMA,
memory placement, timing, persistence and listening remain unverified. No
dependency/upstream changes, hardware transfer, commit or publication occurred.

## Reproduction

Use fresh ignored output paths and configured launchers:

```sh
./labctl doctor
python3 scripts/build-sketch-device.py out/runs/YOUR-CLOCK-BUILD --arm-diagnostics --clock-fix
python3 scripts/check-sketch-boot-upload.py out/runs/YOUR-CLOCK-BUILD \
  out/runs/YOUR-CLOCK-UPLOAD --native-upstream /absolute/path/to/digikit-at-38dfbe4
python3 scripts/check-native-sketch.py out/runs/YOUR-CLOCK-STARTUP \
  --build out/runs/YOUR-CLOCK-BUILD --upload-proof out/runs/YOUR-CLOCK-UPLOAD \
  --boot-only --arm-diagnostics --native-upstream /absolute/path/to/digikit-at-38dfbe4
python3 scripts/check-native-buf-recording.py out/runs/YOUR-CLOCK-RECORDING \
  --clock-only --native-upstream /absolute/path/to/digikit-at-38dfbe4
python3 scripts/package-sketch-arm-diagnostic.py out/runs/YOUR-CLOCK-BUILD \
  out/runs/YOUR-CLOCK-UPLOAD out/runs/YOUR-CLOCK-STARTUP \
  out/runs/sketch-experimental-20261023-01/package out/runs/YOUR-CLOCK-PACKAGE \
  --clock-proof out/runs/YOUR-CLOCK-RECORDING
```
