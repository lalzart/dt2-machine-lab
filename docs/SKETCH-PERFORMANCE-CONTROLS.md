# Sketch BAR/NOW and native page exits — OS 1.16

The user reports that the selector experimental firmware works on their device
and the core BUF workflow is present. This is a user report, without installed
hash readback. The protected package is
`fe1772ac49b694d0d259d0c7b8b2a673db4901de3ec912428a1be965ebbdc3de`.

The new opt-in `--performance-controls` profile requires the working clock
profile. Sketch encoder F selects START BAR (default) or START NOW. The setting
is one volatile menu value, survives closing/reopening, resets to BAR at boot,
and is independent of recorder DEST and BUF selection. An admitted capture
locks this control; it does not gain per-buffer presets or persistence.

BAR retains the existing next-bar service. NOW passes the same guarded two-arg
admission, then the existing GUI poll starts the native recorder without waiting
for a new bar receipt. Its selected 16/32/64 steps begin at that actual start.
Duration uses the authenticated OS1.16 getter at `0x4002d744` (BPM*120) and the
native sample clock. A bounded quarter-note accumulator avoids overflow at all
supported lengths. Tempo change or lost GUI cadence cancels this initial NOW
slice. Playback/normal16/source/context guards and the ten-second cap remain.
Stopped capture is outside this first slice. Publication never assigns tracks.

Native replacement testing exposed an existing-controller completion race:
after a 113,408-frame NOW take, the controller entered normalization before
the adapter's manual STOP. The adapter treated native state 3 as cancellation
and discarded it. The opt-in profile now validates the completed count against
the latched duration/tempo before adopting native state 3/4. It never issues a
second STOP. The count must fit the selected length within the 64-frame native
counter margin and existing late-stop bound; short/overlong takes, tempo changes
and explicit cancellation remain rejected. The exact failed trace is a focused
instruction regression. DSP and publication code are unchanged.

The six native page-button IDs 1–6 close only the actual Sketch view owner on
press and return the event to the normal page handler. Releases/repeats and
earlier modal owners retain their existing handling. Leaving the view does not
cancel a valid capture. STOP and NO keep the original cancellation paths.

The reported B17 is the backing ordinary sample slot. The quick list aliases
already identify BUF1–4, while the compact SRC field still uses that slot name.
Static source/format references do not yet prove a narrow compact-field hook;
this lower-priority display change is deferred. No sample renumbering or A-minus
namespace is introduced.

The new code/state fits the existing reserved arenas; DSP, PCM allocation,
generation/FREEZE/publication and stock recorder destination remain unchanged.
Omitting the new flag reproduces preceding selector MAIN
`701a29543c5da385cd607bc5f8f2586742e3089e98165fd8854d6586dcdd9795`.
Focused instruction checks and a bounded native recording/menu flow are the
acceptance gates. Emulator cadence/input and physical hardware remain separate.

## Current validation and package

[Experimental R2 package/use notes](../out/runs/sketch-controls-experimental-01/package/README.md)
contains `EXPERIMENTAL_SKETCH_BUF_CONTROLS_R2_OS1.16.syx`, SHA-256
`1884e1079c629dad7a41dac1bb7db9ddfea1a04f0306a70c37c48de4decffe8b`.
MAIN is `7b3c783fcedd97fa459fb5005c73d3cc0978107acdf98cd37ce7ad209fc22d66`.
It is byte-identical to the final native-tested container. The original sibling
checkout is read-only in this session; changes and the source patch are staged.

- Ten focused controls tests and fourteen selector tests pass through the
  explicit Rust ColdFire bridge. Native completion tests use the failing count,
  guard against a second STOP, test all supported lengths and reject short,
  overlong, changed-tempo and explicitly canceled completed takes.
- [Final native flow](../out/runs/sketch-controls-final-01/report.json) passes
  BAR capture/publication followed by NOW replacement, all six page exits,
  exit during capture, volatile selection retention, native-completion adoption,
  source PCM, assignments, NORMAL DEST, code/canaries and zero missing blocks.
  NOW records 113,440 frames against a 112,942-sample target in this model.
  These sample-clock measurements are not physical timing evidence.
- [SINE compatibility](../out/runs/20261023T141007Z-test-a6230929/manifest.json)
  and [fresh upload/stream checks](../out/runs/sketch-controls-upload-02/report.json)
  pass with final source hashes intact. No dependencies or DSP bytes change.
- Earlier `sketch-controls-native-01` and `sketch-controls-replace-diag-01`
  remain failed: they captured then discarded the full replacement. The latter
  records native state 3 at cancellation with unchanged capture settings and
  no adapter STOP call. The separate empty-NOW diagnostic passed. They retain
  the evidence that led to the completion correction and are not final passes.

The new image has not been transferred or tested on hardware. Playback/stable
tempo, normal16/scale qualification, the ten-second cap, compact SRC naming,
startup sample-loading wait and absent project/+Drive persistence remain the
stated limits. The unchanged previous image has the user's positive device
report; this R2 image requires its own device test.
