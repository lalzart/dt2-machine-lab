# Flex Lite: one temporary sample in prepared OS 1.16

2026-10-06. Frozen contract for the authorized experiment.
Proposal: [Flex Lite feasibility](FLEX-LITE-FEASIBILITY.md). The user approved
temporary sample allocation, assignment, stock playback and safe replacement.
Project persistence and live recorder capture remain later work.

## Frozen scope and evidence

Working artifact: `scripts/probe-flex-lite.py`, with lab-owned adapter
`lab/flex_lite.py`, a fresh ignored report, control traces and rendered WAVs.
The result is prepared CPU execution and offline SHARC voice-buffer audio.
No firmware-container build, device action, real-time or final-mixer claim.

Architecture: offer immutable synthetic PCM through a RAM-backed input adapter
to the original 1.16 loader at `0x40154540`. Intercept only the source-reference,
open/read/size/name/close boundary for the temporary resource. Execute original
allocation, alias bookkeeping, stereo deinterleaving, page/header production
and unload code. Existing DigiKit bounded-call accommodations (mutex, event,
eMMC overlay and transfer capture) remain explicit. No new DSP algorithm.

This is an emulator prototype of a volatile resource, not a hardware-ready
patch. A temporary identity exists only in the adapter's session. The resource
must never become a persistent project reference. The normal stored sample
path is an independent comparator. Dependencies stay pinned and unchanged.

The sample loader's allocation vector is at `0x405a0f64` (0x34-byte records),
slot-to-block map at `0x405b5368`, slot clear at `0x40153bea`, and unload at
`0x401540c6`. These were inspected in authenticated 1.16 disassembly. The
prototype must inspect actual records and select an unused nonreserved slot;
the preview slot and bank-zero slots are unavailable.

## Experiment and acceptance

- Pin MAIN/BLOB, dependency/runtime, snapshot, source and fixture hashes.
  Record exact accommodations and any controlled control-frame edits.
- Use deterministic mono and stereo int16 PCM at 48 kHz, distinct channels,
  bounded length at most 20,000 frames. Frozen numeric oracle: byte-exact
  source PCM after transport and float32 voice-output equality under identical
  state and controls for RAM-backed versus real file-backed loading.
- Verify independent allocation, extent bounds, guard space, page ordering,
  slot metadata and stock slot isolation. No hardcoded vacant SDRAM address.
- Check the five **16-bit samples** (10 bytes) copied into each channel's
  interpolation guard. Original SHARC `0x1c400f` uses short-word transfers at
  offsets 0 through 4; a fresh publication also showed exactly 10 copied bytes.
  An earlier 20-byte assumption failed in `flex-lite-05`; retain that run.
- Instrument storage: temporary loading and unloading must issue zero eMMC
  operations. Emulated comparator files are local test fixtures only.
- Publish pages before the live slot header. Deliver transfers through the
  stock SHARC LP0 completion callback; no direct sample-pointer injection.
- Select the resulting slot for track 1; explicitly distinguish guest CPU
  assignment, wire selection and offline DSP playback in the report.
- Exercise pitch, start/end and looping, with finite nonzero outputs and
  audible-condition changes relative to base. Retain exact-repeat and an
  unpublished-slot negative. Extend to reverse if the stock controls support
  it in this bounded fixture.
- Pitch semantic checks allow `1e-7` sample/frame rounding error. A diagnostic
  run measured stock +12-semitone step `0.9999999403953552` instead of exactly
  1.0, consistent with its floating-point exponent calculation. The separate
  RAM/file audio comparison remains byte-exact; no expected PCM is rewritten.
- Replacement policy: stop/detach both track lanes before retiring the old
  allocation. Publish a new generation and retrigger. Refuse replacement of
  an active resource. A different PCM generation must produce different audio.
- Bound CPU calls and DSP blocks; retain failed runs. Run scoped lint, source
  harness unit tests and the repository-required SINE replay regression.

The host RAM source may use the native sample header as an internal envelope;
that is a byte format, not a persisted +Drive file. It does not establish
audio-input recording. Optional save, project metadata/lifetime integration,
all-track operation and panel UI are out of this first slice.

## Reporting

Keep final results separate from this frozen contract. Report exact evidence if
stock loader or playback boundaries
cannot be crossed without broader changes; do not relabel a synthesized wire
stream as actual CPU assignment or a stubbed file path as actual storage.
