# Plaits macro controls

Implementation results for the frozen [contract](PLAITS-CONTROLS-CONTRACT.md).

## Transport amendment, 2026-10-05

The real CPU probe `out/runs/macro-panel-probe-05/capture.json` demonstrated
that HARM and MORP locks store and recall, but the borrowed sample slot reduces
TIMB to ten bits: raw locked 5639 became 519 on the trigger frame. No DSP input
was substituted in that observation. The stock sample-slot transport cannot
carry this continuous macro reliably.

The controls variant therefore extends the existing track-1/type-7 MODEL shim
to copy HARM/MORP after stock filtering. TIMB is copied after the complete
sample bank/index repacking loop at `0x4002e9a0`, including its 1024 sentinel
branch. Other machine types and tracks retain their previous path. All three
macros reach the same outgoing frame and update immediately on the
CPU side; the unchanged Plaits engines retain their own interpolation. This
also gives locked triggers coherent values without an inherited base-to-lock
smoothing transient. Prepared runtime and stock parity checks follow below.

## Controls and source

The separate `plaits-controls` family reuses the six existing MAIN engines.
It adds a wrapper that reads the macros on every 32-source-sample voice call;
MODEL, pitch, length and level still latch on the trigger. Engine source,
lookup tables, envelope, gain cap, two-lane layout and MIT notices are unchanged.
The old bank remains an exact build/PCM comparator.

| Encoder | Label | Parameter ID | Raw range | Metadata default |
| --- | --- | --- | --- | --- |
| B | HARM | 275 | 0..32512 | 16384 |
| D | TIMB | 276 | 0..32512 | 16384 |
| E | MORP | 277 | 0..32512 | 16384 |

The numeric display uses 0..127 with eight fractional bits; DSP normalization
is raw/32512, clamped to 0..1. Encoder C remains MODEL 0..5. See the
[bank model map](PLAITS-BANK.md) for each engine's macro meanings.
`machines/plaits-controls/controls.json` supplies the CPU rows and generated
adapter constants. The source lock pins the contract, control map, all 42
upstream files and 21 reused lab files. A source mismatch stops validation.

Three sparse parameter rows preserve the original stock macro definitions.
Expected-byte guards identify each replaced ColdFire table reference, its
bound check and required setter/UI behavior. The new IDs reuse numeric UI
behavior; stock-only cache initialization loops retain their original limits.
This is a version-specific OS 1.16 patch, not a general machine plug-in API.

## Repeat

Use a fresh directory. The single command builds both images, checks CPU
helpers and compiled adapters, captures encoder/lock gestures from the prepared
CPU checkpoint, renders genuine captured frames through the SHARC voice hook,
and writes `report.json` and `plaits-controls.wav`:

```sh
python3 scripts/try-plaits-controls.py out/runs/macros-new --play
```

Without `--play`, it only writes the audio. For a quicker adapter preflight or
to reuse a passing CPU capture:

```sh
python3 scripts/try-plaits-controls.py out/runs/macros-check-new --checks-only
python3 scripts/capture-plaits-controls.py out/runs/macros-capture-new
python3 scripts/try-plaits-controls.py out/runs/macros-render-new --capture out/runs/macros-capture-new
```

`--regenerate-header` explicitly regenerates `controls.h` before verification;
ordinary runs check that the generated header matches the locked control map.

The CPU capture requires the existing
`out/runs/controls-cpu-lock-fast/locked-ready.snap` and configured private CPU
inputs; `--snapshot` on the capture command accepts the same prepared state at
another path. Adapter compatibility also checks the retained bank-final-01
report. These are explicit fixture dependencies, not clean boot reconstruction.

The audition plays locked A, locked B, base, then a captured HARM edit during
one note. It uses completed, buffered WAV audio. Raw capture, sequence replay
and held-tail audition are distinguished in the report; only other-track
one-shot event bits are masked. Parameter values are never substituted for a
passing render. Deliberately frozen controls are a separately labeled negative.

## Remaining boundaries

This establishes the prepared track-1 experiment only. Normal PLAY traversal,
project save/reload, cold startup, all-track use, physical timing and final
mixer/DAC output remain open. The CPU page still uses the inherited layout;
LCD captures can contain partial redraws. Numeric metadata defaults are checked,
but a real panel reset gesture and fresh-machine default initialization are not
established. The prepared checkpoint retains its old values until edited.
No hardware image container is generated or flashed by these commands.

## Focused validation

The CPU checks exercise 3,372 sparse-resolver/register cases, complete
mirror/owner/flag/kind readers, numeric UI lookup and min/max validation for
old/new/fallback IDs. The original 275 rows remain byte-identical except the
pre-existing MODEL customization. Dedicated metadata defaults are checked.
The transport checks cover 368 type/value/flag combinations, including the
sample-slot 1024 sentinel, and require untouched registers, flags and other
track memory outside the displaced instruction effects.

All six compiled adapters pass fresh-state exact repeat, retrigger, unchanged
note age during macro edits, trigger-latched MODEL, independent lanes,
switch-away clearing and silent return. Their zero-macro endpoint audio is
bit-identical to the old bank; rebuilding the old bank reproduces its image.
A frozen-macro WS negative differs, confirming that live parameter changes
reach the compiled engine. These are focused integration checks, not a new
upstream DSP test suite.

The eight harness tests and Python lint/format checks pass. The required SINE
regression passed in `out/runs/20261005T133821Z-test-75d20dd2/manifest.json`,
including exact baseline PCM, stock parity and negative controls. It ran after
the DSP/control adapter changes; the later CPU-only sentinel refinement was
checked separately before the final macro capture.

External MIDI and LFO destination assignment have not been established for
the three new parameter IDs. The original stock metadata and cache loops
remain available to stock machines.

The guarded CPU payload now ends exactly at `0x40312000`, the start of the
boot-cleared region. The builder refuses any spill into that region or into
neighboring labels/helpers. Additional CPU code will require deliberate space
planning. `macro-cpu-patches.json` records every expected before-byte sequence,
replacement, helper address and sparse reader site for review.

## Completed run

`out/runs/macros-final-01/report.json` passed the complete single-command run
in 557 seconds on this Mac. Its `capture/` directory contains the original
630 CPU frames, source/input hashes, snapshot and screen captures, with zero
faulted pages or worker error. Eight different HARM base values were observed.

| Preview | HARM raw | TIMB raw | MORP raw |
| --- | ---: | ---: | ---: |
| Locked A, step 5 | 31232 | 24583 | 7424 |
| Locked B, step 13 | 19456 | 10247 | 0 |
| Unlocked base, step 9 | 24576 | 16391 | 1280 |

A/B/base/A/base recalls matched these actual trigger words. The 633-frame
prepared SHARC sequence repeated bit-for-bit. Matching-input prefixes for
A recall and base recall matched for 1664 and 1600 interleaved samples.
Stock-hook PCM parity, disabled-hook negative and frozen-HARM negative passed.
The sustained edit contains exactly one CPU trigger. A separate compiled
Params probe confirms all three full values reached the DSP adapter, including
TIMB 24583/32512; see `macro-transport-probe.json` in the same run.

`plaits-controls.wav` plays A, B, base and the sustained edit; its unscaled
voice-buffer peak is 0.08463. `macro-lock-sequence.wav` retains the shorter
preview sequence with documented preroll/tail adaptation. These are executed
SHARC voice-buffer captures, not host-engine substitutes or final mixer output.

CPU image SHA-256:
`0b2ed931ec1d81f02f275070a0b04fa6d6cf4020f4386bb6affb18ae51445eb5`.
Audition float PCM SHA-256:
`d8f73d0af6d8eef7591d03c791e3663e0c31c1e533a021552ad30c1edfb74294`.

The full report initially undercounted transport cases as 48; all 368 actually
executed. The count and configured-fixture path handling were corrected in the
checker, and every CPU check was rerun in `cpu-recheck.json`. Firmware, DSP and
capture source were unchanged. The original full report remains preserved.
