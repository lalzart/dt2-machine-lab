# Three-model Plaits prototype

Approved by the user's “Sounds good, let's do it” after the VA / two-operator
FM / bass-drum proposal. This is an incremental source port in the machine lab.
The existing VA reference and optimization variants remain available unchanged.

## Frozen implementation contract

Working artifact: `out/runs/<unique>/plaits-trio.wav`, plus CPU/DSP image overrides
and a comparison report. Evidence sought: host signal, compiled SHARC execution,
prepared track-1 voice PCM, and CPU model-lock transport. Physical timing,
final output, clean startup and the complete 24-model catalogue are outside this
slice. Use the repository-native source lock, control map, retained run reports
and this note instead of adding a general testing framework.

Authority: the existing pinned eurorack and stmlib revisions, exact files in
`machines/plaits-trio/source-lock.json`, and the existing VA C translation.
MIT notices remain in all adapted DSP/table files. The source checkouts and
pinned toolchain must remain clean. Equations, original lookup literals,
47872.34 Hz pitch calibration, 48 kHz processing and 12-sample blocks are
preserved. A C99 adapter replaces C++ objects/destructors. Only MAIN is used:
FM's AUX sub oscillator and the bass drum's independent synthetic AUX are
excluded; compare MAIN against the complete original engines. The full module's
LPG and CV processing are not part of this prototype.

IDs 0/1/2 select VA/FM/BD. A common note, HARMONICS, TIMBRE, MORPH, trigger and
accent interface calls the selected engine. Inputs clamp to documented ranges.
A fixed union owns the active engine state; no heap or global random state is
needed for these MAIN paths. Init/reset zeros the union, then initializes the
selected engine. Switching models occurs on a trigger and replaces the old tail.
Retrigger resets the current engine too, preserving the existing lab's repeatable
note convention. Panic/type switch clears activity; a return without a trigger
is silent. No freeze, reconnect protocol or retained polyphonic tails in this
slice. Invalid model values clamp to a valid model. No runtime variant swapping.

The firmware wrapper keeps independent track-1 lanes and the existing 48-to-96
kHz duplication/FIFO adapter. It uses the existing short lab envelope for VA/FM;
BD uses its original internally enveloped MAIN, with only a final length gate
and 5 ms fade-out. Level remains capped at 0.125. Core comparisons occur before
that wrapper. Shared-lane caching is not automatically inherited by new engines.

The authoritative control map is `machines/plaits-trio/controls.json`; generate
C register/scale constants from it. Use the dormant C/CFADE row for MODEL, set
its raw range to 0/256/512 for the three discrete models (8 fractional bits). Existing borrowed macro controls remain
experimental; verify their actual frame positions rather than assuming slot
order. CPU label/range improvements must be distinguished from waveform and
transport proof. Raw captures are retained; synthetic frames are explicitly
labelled and never presented as genuine parameter locks.

## Literal checks before acceptance

- Verify upstream hashes/revisions, MIT closure, and regenerated source/table
  bytes. Retain the proposal hash and source/fixture/compiler/image hashes.
- Original C++ versus C99 MAIN for each model: 4,000 blocks/one second,
  settings (48,.25,.3,.4), (60,.7,.8,.2), (36,.9,.1,.8), then first setting,
  changes every 1,000 blocks. BD rising edges at blocks 0/1000/2000/3000,
  accent .8; VA/FM ignore trigger. Repeat initialization exactly. Check all
  16 note 0/127 and macro 0/1 corners over 120 blocks. Host max error <=1e-5.
- Standalone compiled SHARC: fresh 120-block vectors, changes every 30 blocks,
  same settings/triggers; max MAIN error <=2e-3 and finite output. Record long
  divergence separately if measured; do not silently relax thresholds. Record
  retired instructions by model, not device cycles or utilization.
- Deterministic integrated model/control changes and real CPU MODEL lock
  capture where possible: latch only on trigger, VA→FM→BD→VA, unequal lanes,
  mid-note selector edits, retrigger, switch-away and silent return. Repeating
  a note from fresh state must reproduce the same PCM. Compare common-wrapper
  VA with the existing MAIN-only build on equivalent semantic inputs.
- Stock type-6 hook parity and disabled-hook negative comparator. A wrong model
  must differ from the selected non-silent model. Preserve failed runs.
- Existing eight harness tests and SINE replay suite. Keep source files fixed
  during final runs so freshness checks remain meaningful.

UNRESOLVED: long target numeric comparisons beyond the short vectors, physical
resource budget, complete model/parameter display and persistence, macro panel
mapping, continuous sequencer traversal, runtime memory ownership and final mix. A failure
at one layer cannot be described as success at another.

## Results

2026-10-05: [the complete run](../out/runs/trio-final-01/report.json) passed.
The [real CPU capture](../out/runs/trio-model-capture-02/capture.json) recalls
MODEL raw values **0, 256, 512, 0** on four trigger frames, with zero faulted
pages and no CPU worker error. UI labels and raw/base mirrors were retained
alongside screenshots, control frames and the prepared checkpoint.

The 707-frame prepared SHARC replay detects **VA/FM/BD/VA** at frames
163/214/264/317. All four intervals contain non-silent PCM; peaks are
0.04492/0.02067/0.10294/0.04492. Returning to VA matches its first 3,264
interleaved samples exactly. Full capture repeat and stock-type-6 hook parity
are exact. Disabling the hook changes PCM (maximum difference 0.34131).
The replay retires 195,822,304 block-handler instructions; this total includes
stock work and different note lengths, so use the standalone table below for
the bounded engine comparison.

The direct compiled-adapter checks also pass: reset/repeat, model latching,
unequal lane models without cross-lane state writes, switch-away clearing,
silent return, wrong-model negative comparator, and exact existing VA PCM on
matched semantic controls. The existing MAIN-only VA image is byte-identical
to `plaits-optimization-final/firmware-main-only/PLAITS_BLOB.bin`.

Artifacts: [emulated voice preview](../out/runs/trio-final-01/plaits-trio.wav),
[three-second host preview](../out/runs/trio-final-01/plaits-trio-host.wav).
The former preserves the short real CPU preview spacing; the latter offers
longer examples of each engine and is explicitly host audio.

The eight existing harness tests, lint/format checks, deterministic source
regeneration, and [SINE replay regression](../out/runs/20261005T082651Z-test-a0ec5c52/manifest.json)
also pass. The final report records the complete source fingerprint at validation;
the later listening script is a separate addition. Generated outputs and source checkouts remain
local; no commit, publication or hardware flash was made.

CPU image SHA-256:
`fcd039cd529459f1f92a6ecb5cbdc35db02ea4bee3e3c012e1e3d6db5c500a7d`.
DSP image SHA-256:
`9cfdb89f01c284db3ea28d449973801eea96f62e3f14ac5d29d82e8ffd64fc73`.
Voice PCM SHA-256:
`ccb48025f582b0c8d7aad8d3a989b0d6ca0825966a0baab09deba14732527f2e`.

The failed `trio-model-capture-01` remains available: encoder delta 1 did not
advance the model. A separate scaling probe exposed smoothing of an enum;
the dedicated CPU shim resolves that without changing other parameters.

## Port and compiler notes

The source-port checks now pass for all three engines. Host MAIN is bit-exact
against the complete original C++ engines for each one-second vector and all
16 corners. The original engine pitch calibration is retained. Reset/repeat
is exact on both the host and the compiled target.

| Engine | Short SHARC max absolute error | Mean instructions / 12 samples | Maximum observed |
| --- | ---: | ---: | ---: |
| VA | 4.98e-6 | 10,761.70 | 11,620 |
| Two-operator FM | 2.29e-5 | 21,535.52 | 22,410 |
| Analog bass drum | 2.18e-6 | 9,247.71 | 10,110 |

These are the frozen 120-block parameter vectors, not a worst-case workload
survey, device cycles, or utilization. FM costs about twice VA on this vector;
only the selected engine renders. The integrated image contains 23,154 code
bytes and 5,196 data bytes. Two independent lane states total 696 bytes.
The loader still reserves the existing experimental 466,944-byte arena;
stock-loader disjointness does not establish runtime memory ownership.

The pinned experimental C compiler required four explicit adaptations:

- Use an explicit tagged union; hiding that union behind a typedef produced
  incorrect member offsets in the first target probe.
- Fold the original float32 FM `a0` expression to its exact literal in the
  generator; the compiler otherwise emitted a zero global initializer.
- Spell unsigned float conversions explicitly using signed conversions and
  the high bit, retaining round-to-nearest behavior. Native FLOAT/TRUNC are
  signed; an implicit conversion corrupted the FM phase.
- Check every emitted table word against its upstream float32 value. The
  compiler negated positive IEEE bit patterns as integers for negative array
  literals (`-1.0` became the bits for `-4.0`). The build adapter accepts only
  correct bits or that exact known error, repairs the latter, and rejects other
  output. Original generated table literals and pinned dependencies stay intact.

`trio-target-first`, `trio-target-constant`, and `trio-target-unsigned` retain
those failed probe builds. `trio-target-tables` first passed all three short
vectors. `trio-core-01/report.json` is the first complete repeatable core run.
The compiler also warns about `SoftClip` reaching the end of a non-void
function; its copied if/else branches all return, and the engine comparisons
exercise this code without changing its equations.

## Discrete MODEL transport

The stock mirror filter uses a one-pole smoother. MODEL must bypass it:
intermediate numeric values are meaningful for timbre but cannot reliably
select an engine at a locked trigger. The CPU candidate adds a 40-byte shim
at `0x40311d04`, entered at the guarded six-byte return-value instruction
`0x400d9346`. Only track 1 with machine type 7 copies raw mirror 27 to its
smoothed counterpart. Other parameters and stock machine types keep their
original path. The displaced return value is restored before continuing.
A focused ColdFire execution check covers types 0..7 and values 0/256/512,
checking the entire destination region and all other data/address registers.

MODEL's label is numeric: 0=VA, 1=FM, 2=BD. Dedicated text names, general
multi-track allocation, the full Plaits LPG, all engines, and AUX remain future
work. HARMONICS still borrows PLAY's four positions, TIMBRE borrows SAMP, and
MORPH borrows SLICE. Do not present those as a finished macro control surface.

## Repeat commands

Use a fresh run directory each time. The configured Python automatically uses
the pinned patched Unicorn environment; do not replace it with `uv sync`.

```sh
./labctl doctor
python3 machines/plaits-trio/translate.py .local/sources/eurorack
python3 scripts/try-plaits-trio.py out/runs/trio-core-new --stage core
python3 scripts/capture-plaits-trio.py out/runs/trio-capture-new
python3 scripts/try-plaits-trio.py out/runs/trio-check-new --capture out/runs/trio-capture-new
./labctl test sine --replay
```

The capture command defaults to the preserved full-timer checkpoint
`out/runs/controls-cpu-lock-fast/locked-ready.snap`; `--snapshot` can select an
identical prepared SINE state elsewhere. It restores under the inherited image,
verifies every changed byte, then applies the CPU candidate's image diff in RAM.
It sends real encoder and step-preview button events, stores FM on step 1 and BD
on step 5, and recalls VA/FM/BD/VA using steps 9/1/5/9. Encoder delta 4 advances
one model in this prepared context; smaller deltas were quantized away. The
panel's transient readout can lag while a trig is held; acceptance uses actual
captured trigger-frame words. Existing pitch/length/level locks remain on step 1.

The CPU candidate is `PLAITS_MAIN_OS.bin`; the integrated DSP candidate is
`firmware/PLAITS_BLOB.bin` under the check run. These are emulator overrides,
not a hardware firmware package. `plaits-trio.wav` taps the two prepared
track-1 voice buffers (represented as stereo). `plaits-trio-host.wav` is a
separate three-engine host preview: one second per engine plus short silence,
with four parameter settings within each second and fixed preview gain 0.2.
Neither file is a recording of the final DTII mixer or physical device.

## Buffered listening in the emulator window

`scripts/listen-plaits-trio.py` opens the prepared CPU snapshot in DigiKit's
front-panel GUI. Preview VA/FM/BD sends real step-preview buttons for steps
9/1/5. Each captured track-1 trigger supplies the controls to the native SHARC
emulator, which renders the note before macOS `afplay` plays it at 48 kHz.
Replay last plays the completed WAV immediately. The first VA note is automatic.
Close the window to stop; the session also closes after 15 minutes.

```sh
cargo build --release --locked \
  --manifest-path .deps/digikit/native/live/Cargo.toml \
  --target-dir out/cache/live-audio
python3 scripts/listen-plaits-trio.py out/runs/trio-listen-new
```

This local launcher uses the checked images in `trio-final-01` and prepared
snapshot/capture in `trio-model-capture-02`. It verifies image and input hashes,
the snapshot's candidate flash bytes, and native pack/card provenance. Each
note retains its genuine trigger frame, WAV, hashes and render statistics in
the fresh output directory. The held frames after that trigger are synthesized
with one-shot events cleared; this auditions separate complete notes and does
not establish continuous sequencer or final-mixer playback. Other tracks are
excluded. Existing FM pitch/length/level locks make its preview shorter/quieter.

The native live-source probe in `trio-live-probe-01/report.json` reproduced the
checked replay prefix byte-for-byte, but took about 31 ms per 0.667 ms audio
block, roughly 2% of real time. The buffered session `trio-listen-03/session.json`
rendered VA/FM/BD without SHARC stops and invoked playback on the default Mac
output. VA/BD notes were 0.267 seconds and FM 0.144 seconds including trailing
silence; rendering took about 8–14 seconds, plus slow CPU panel handling.
This is actual emulated voice-buffer audio. Real-time streaming, final mixer
output, physical timing, and physical-device operation remain unverified.
After adding the launcher, the eight harness tests, launcher lint/format checks,
dependency doctor and SINE regression passed again; the regression report is
`out/runs/20261005T085729Z-test-a007e253/manifest.json`.
