# Startup recording experiment — OS 1.16

The existing stock recorder can capture external input during native project
sample loading in the emulator. A completed take can remain in recorder
storage while later samples load, then pass through the existing native BUF
worker into H124. No firmware, allocator, DSP, admission guard or upstream
source was changed. Sketch's early ARM remains blocked in the packaged R4 OS.

This is a feasibility experiment through the original SAMPLING view and its
native C DEST control, with manual START, STOP and later USE. It does not
implement automatic early recording, BAR timing or a new pending-take service.
External PCM and peripheral cadence remain modeled. No hardware transfer,
physical startup timing, listening or final-output qualification was performed.

## Observations

| Bounded run | Result |
| --- | --- |
| `startup-survey-01` | Passive reset-to-startup trace, zero captures. 297 outer project-load calls; native code/canaries intact. Filesystem verification overlaps loading on the original fresh card. |
| `startup-panel-verified-02` | One external-input capture begins inside a real active load, with 241 later loads still to start. It overlaps 242 project-load calls and stops after the batch. Recorder PCM retained; this slice performs no PCM readback or BUF publication. |
| `startup-retain-publish-01` | One 9,600-frame stereo capture starts inside loading and stops with 113 later loads still to start. The complete take survives those loads, then native USE performs 19 contiguous PCM readbacks, an owned CPU copy and one BUF 1/H124 publication. |
| `startup-analysis-controls-01` | Real positive accepted; four analytical negatives rejected: a button sent early with native START delayed until after loading, wrong source, STOP after the batch, and corrupt owned PCM. Zero captures. |
| `startup-cancel-01` | Failed control retained. Native NO after early STOP yields no observed BUF publication, but discard is not demonstrated. The probe stops at an overly strict assertion forbidding even empty BUF setup; actual setup was 1 and publication count remained 0. Cancellation is unqualified. |

In the retention/publication slice, START occurs during project load 95, STOP
during load 184, and all 297 project loads finish before native readback/USE.
Ninety load calls overlap the active capture, and 113 begin after STOP.
At the later post-STOP checkpoint, 220 loads have begun and playback setup and
publication are both still zero. These are different observations at different
instruction boundaries; 77 versus 113 remaining is not a count discrepancy.

Before capture, the recorder defaults to NORMAL. Native encoder C explicitly
selects BUF 1. Playback slots are still uninitialized at START and STOP; capture
does not need their allocation. The source getter returns raw 18, whose stock
OS 1.16 label is IN. Native readback/copy confirms stereo data. No host writes
to DEST, counters, locks, jobs, sample associations or publication state occur.

Native CPU copy output is 38,480 bytes: a 64-byte native header, 38,400 PCM
bytes and a 16-byte trailer. Its PCM matches the modeled external source and
retained recorder take exactly. The 19 readbacks cover frames 0–9,599 once,
under the existing recursive-lock contract; shared response scratch is poisoned
on unlock by the unchanged recorder peer. The owned-copy observation uses
native COPY return registers and reads memory at the following trace drain;
it is not a stopped-at-instruction memory snapshot.

The live DSP descriptor for H124 is `[8224, 28704, 19200, 48000, 1]`.
Both channels have the expected length. Publication preserves all 16 sample
assignments. The original DSP executes sample loading and descriptor updates;
this experiment does not trigger/audition the new take or add a new voice-PCM
comparison. R4's separate playback evidence remains at its documented scope.

## Fixture and evidence boundaries

The first native fixture boots an unverified card and displays VERIFYING FILE
SYSTEM while project samples load. Native verification writes were exported
before the later recorder control. Applying only those masked guest writes to
a fresh copy creates the subsequent-boot card fixture; the original card is
unchanged. This next boot has no verification dialog over the load window.
No clean-card flag or project data was invented by the harness. The overlay
comes from `startup-panel-fresh-02`, whose later button control failed; this
does not turn that parent run into a pass.

For the subsequent-boot fixture, `relax_fs_check` changes only the host's ready
classification to main-panel readiness. It does not bypass a firmware dialog,
skip native verification or alter any guest guard. The probe separately waits
for the actual project worker return and quiet operation/LP0 state before USE.
A zero count between two loads is never used as whole-batch completion proof.

Two early panel attempts used PAGE where their labels said SAMPLING:
`startup-panel-fresh-02` and `startup-panel-verified-01`. They remain failed and
are excluded from recorder claims. The corrected driver extracts the exact
control names from authenticated stock 1.16 MAIN and refuses a changed map;
SAMPLING is code 50, PAGE 22, YES 10 and NO 12. Build failure
`startup-panel-fresh-01` was a Rust observer borrow error before execution.
No accepted recording or firmware result came from those attempts.

The passing recorder and publication probes and their frozen Rust sources are
retained in their own run directories. The separate cancellation source is a
small derived probe, with its complete diff saved outside production source.
Its addition does not change the compiled source of the passing probe. Its
NO-only result must not be described as validated transaction cancellation.
The request was sent during normalization; no discard appears in the saved
startup trace, and the settled trim screen still contains the take and labels
FUNC+NO as DEL. Bare NO is not a demonstrated delete gesture here. The future
Sketch pending transaction needs its own explicit invalidation policy.

## Architecture decision

Proceed with separate capture and publication ownership for Sketch. The
experiment supports earlier capture without a new PCM pool for this particular
startup problem. A physically separate pool remains a different modularity and
capacity decision; it is neither proved necessary nor ruled out by this test.

The next implementation should own at most one pending transaction, latch BUF,
project/kit identity and capture settings, and protect the retained take from a
second recording or conflicting recorder action. It must distinguish CAPTURED /
WAITING TO PUBLISH from playable BUF READY. Publication still needs qualified
exclusive access to shared loading/allocation. Keep the prior committed take
until successful publication and reject occupied H124–H127 without overwriting.

Implement cancellation/project replacement as explicit transaction invalidation,
with no later automatic publication from a stale callback. Preserve normal
recorder behavior even where stock NO retains audio. Test those ownership rules
before exposing automatic startup ARM in an OS package. This experiment does
not qualify capture during an actual filesystem-verification modal, overlapping
FREEZE, a second capture, project replacement, old BUF readers, BAR timing or
publication before the complete startup load batch has returned.

## Reproduction and artifacts

Use the configured Python from this staged lab and fresh output directories:

```sh
"$LAB_PYTHON" -B ../prepare-experiment.py out/runs/UNIQUE --mode publish \
  --card ../fixtures/verified.img
"$LAB_PYTHON" -B ../analyze-startup.py out/runs/UNIQUE
```

The native-write card fixture and its mask/base hashes are recorded in
`../../fixtures/verified.json` relative to this document. The original card is
read-only; all tests use sparse native writes or an isolated copied image.

- [Capture/retention/publication report](../out/runs/startup-retain-publish-01/report.json)
- [Native event ordering and exact PCM checks](../out/runs/startup-retain-publish-01/ordering.json)
- [Recorder screenshot sequence](../out/runs/startup-retain-publish-01/startup-recording-contact.png)
- [Failed cancellation control](../out/runs/startup-cancel-01/report.json)
- [Analysis negative controls](../out/runs/startup-analysis-controls-01/report.json)

Native startup uses the unchanged R4 full container, CPU application reset and
an independently initialized native SHARC DSP, with DigiKit `38dfbe4` and the
existing opt-in recorder peer. DSP ROM/SPI FIFO, physical cache/DMA ownership,
real audio-input transport and wall-clock startup latency remain separate.
The prior R4 OS and all 949 baseline files are preserved. No new OS is built.
