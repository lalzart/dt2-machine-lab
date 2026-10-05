# Six-voice Plaits bank

The `plaits-bank` family adds three MAIN engines to the existing VA/FM/BD
prototype. The previous `plaits-trio` and VA source/build commands remain
available. This is a compiled SHARC source port with the same prepared DTII
OS 1.16 integration, not a change to emulator timing or live playability.

| MODEL | Voice | HARMONICS | TIMBRE | MORPH |
| --- | --- | --- | --- | --- |
| 0 | Existing VA | Existing mapping | Existing mapping | Existing mapping |
| 1 | Existing two-operator FM | Existing mapping | Existing mapping | Existing mapping |
| 2 | Existing analog bass drum | Existing mapping | Existing mapping | Existing mapping |
| 3 | Waveshaping / wavefolding | Waveshaper selection/morph | Folding amount | Oscillator slope |
| 4 | Harmonic additive | Spectral bumps | Spectral centroid | Spectral width/slope |
| 5 | Granular formants | Formant ratio and carrier bleed | Formant frequency | Grain shape |

These are semantic engine controls. The DTII prototype still borrows the stock
PLAY/SAMP/SLICE macro rows and their limited ranges/readouts. MODEL's dedicated
numeric selector now runs 0..5. Every control still latches on a trigger; live
knob sweeps, a polished control page, continuous pattern playback and project
reload are not established by this addition.

## Source and state

The immutable [contract](PLAITS-BANK-CONTRACT.md), exact
[`source-lock.json`](../machines/plaits-bank/source-lock.json), and
[`controls.json`](../machines/plaits-bank/controls.json) define the port.
`translate.py` checks the pinned upstream and reuse hashes before regenerating
C99, headers and tables. The controls file generates C constants and supplies
the CPU MODEL range. Original MIT notices are retained.

WS preserves the bandlimited slope, waveshaper interpolation, frequency-dependent
attenuation and Hermite wavefolder. ADD keeps all 24 MAIN partials and the
original unusual amplitude smoothing/normalization. GRAIN preserves both MAIN
grainlets and their high-pass filter. Independent AUX processing is excluded;
the complete original C++ engines remain the host oracle. No randomness or
sample memory is introduced. The existing full-Plaits LPG/AUX exclusions remain.

The bank directly reuses the VA/trio core rather than duplicating those engines.
Its fixed union is 256 bytes, followed by a four-byte model selector. Two
firmware lanes total 704 bytes, eight more than the trio. Each trigger resets
the selected model and replaces the previous tail. Other lane state remains
independent. Switching to a stock machine clears activity; returning without
a trigger stays silent. The existing short envelope, gain cap and 48-to-96 kHz
buffer adapter are preserved.

## Repeat

Use a fresh output directory each time. The retained `trio-final-01` report and
its exact audio hashes are required as the previous-version baseline. The CPU
capture starts from `controls-cpu-lock-fast/locked-ready.snap` unless an
identical prepared checkpoint is supplied with `--snapshot`.

```sh
./labctl doctor
python3 machines/plaits-bank/translate.py .local/sources/eurorack
python3 scripts/try-plaits-bank.py out/runs/bank-core-new --stage core
python3 scripts/try-plaits-bank.py out/runs/bank-adapter-new --stage adapter
python3 scripts/capture-plaits-bank.py out/runs/bank-capture-new
python3 scripts/try-plaits-bank.py out/runs/bank-check-new --capture out/runs/bank-capture-new
./labctl test sine --replay
```

`--stage core` tests upstream/host/compiled engines; `--stage adapter` tests the
CPU shim and direct compiled voice calls; the default includes those checks
and genuine CPU capture replay. The capture stores WS/ADD/GRAIN locks on steps
5/13/1, then previews VA/WS/ADD/GRAIN/WS/VA using steps 9/5/13/1/5/9. Other-track
trigger/release bits are masked only for DSP replay; selector and macro words
remain genuine CPU output. This is step-preview evidence, not continuous PLAY.

The checked run produces `PLAITS_MAIN_OS.bin`, `firmware/PLAITS_BLOB.bin`,
`plaits-bank.wav` (two emulated voice buffers), `plaits-bank-host.wav` (six
one-second host examples), per-engine host WAVs, raw PCM and `report.json`.
Original firmware stays untouched; these are local emulator overrides.

## Validation results

The first core run `out/runs/bank-core-01/report.json` passed: every engine's
host MAIN matched untouched upstream exactly over the one-second parameter
vector and all 16 endpoint combinations, and initialization repeated exactly.
Short compiled SHARC comparisons also passed. Existing VA/FM/BD host and target
PCM hashes match the previous trio vectors exactly.

| New engine | Short SHARC max absolute error | Mean instructions / 12 samples |
| --- | ---: | ---: |
| WS | 2.38e-7 | 7,677.64 |
| ADD | 1.79e-7 | 30,450.33 |
| GRAIN | 3.74e-6 | 13,233.85 |

These are emulator instructions for a bounded vector, not physical cycles or
CPU/DSP load percentages. Each engine was checked for two exact-repeat
120-block target renders. Only the selected engine runs.

The direct-adapter preflight `bank-adapter-01/report.json` passed six-model
reset/repeat, new-model negative comparison, latching, unequal-lane isolation,
switch-away/silent return and exact old trio PCM. All 48 CPU selector/type
combinations passed the smoothing-bypass check. The rebuilt trio BLOB remains
byte-identical to its prior checked image. That preflight's build metadata used
the old default lane-size label; this reporting field was corrected to 704
bytes for integrated bank builds before the final validation runs.

The SINE regression passed in
`out/runs/20261005T095057Z-test-5569b436/manifest.json`, including its fixed PCM
hash, stock isolation, clone parity, negative control and lifecycle checks.
The eight source-only tests and new Python lint/format checks also pass.

The first CPU capture `bank-model-capture-01` correctly failed: reusing the
trio's delta-4 encoder input with the enlarged range recalled models 4/5/5
instead of 3/4/5. The capture now reads each actual preview-trigger selector
while setting the lock, makes bounded panel-only corrections if needed, and
requires the final independent recall sequence. No expected values were changed
to accept the wrong models. Delta 3 reached all three intended values on the
first readback in the corrected run.

The final [CPU capture](../out/runs/bank-model-capture-02/capture.json) passed
with MODEL raw values 0/768/1024/1280/768/0, no worker error and no faulted pages.
The [complete bank run](../out/runs/bank-final-01/report.json) then passed all
source, compiled-core, adapter, CPU shim and firmware checks. Its 811-frame
replay rendered VA/WS/ADD/GRAIN/WS/VA at frames 164/214/265/315/368/418.
Every interval is non-silent. Returning to WS and VA reproduces 3,200
interleaved samples exactly; the full render repeat and stock hook comparison
are exact. Disabling the hook changes PCM by up to 0.33340.

The final compiled image contains 35,802 code bytes and 12,496 data bytes;
the two lane states total 704 bytes. Compared with trio, that is 12,648 more
code bytes, 7,300 more table/data bytes and eight more state bytes. The existing
466,944-byte experimental loader arena remains reserved. All 1,285 widened
waveshaping table integers were also checked against the emitted assembly.
The pre-existing compiler SoftClip return-analysis warning remains; every
source branch returns and the original BD comparisons continue to pass.

CPU image SHA-256:
`2a3670e959530cab31c748b3e6838cce5c0fade4c4622c5e5885c3396a97c8ba`.
DSP image SHA-256:
`cdb0c1f08b84f07d51ca27b455703b7217cb04770528c3e5660c5efbbec17217`.
Firmware voice PCM SHA-256:
`3049ac70019449beb4a1d74428f06977c115152bae7717ec2bfb3feb3c6bcf8e`.

Audio: [emulated voice-buffer sequence](../out/runs/bank-final-01/plaits-bank.wav)
and [six-second host demonstration](../out/runs/bank-final-01/plaits-bank-host.wav).
The host order is VA, FM, BD, WS, ADD, GRAIN, one second per engine with short
gaps and parameter changes inside each second. The emulator sequence keeps
its short genuine CPU step-preview spacing. GRAIN inherits step 1's earlier
shorter/quieter note locks. Neither file is final mixer or physical-device audio.

The final report's complete source fingerprint matches the finished source
files. Original VA/trio files and both pinned dependencies remain unchanged.
No new general test framework, commit, publication or hardware flash was made.

## Remaining limits

Long target numerical comparisons, worst-case cost, physical resource budget,
continuous live playback, macro UI, persistence, clean startup, runtime arena
ownership and final mixer/DAC output remain unverified. Adding engines does not
resolve the previously measured emulator audio throughput limitation.
