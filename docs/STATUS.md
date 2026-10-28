# Current status

## Combined Sketch, Capicola R2 and ARP — 2026-10-27

The requested optional [combined build](SKETCH-CAPICOLA-ARP.md) includes current
managed Sketch, assignment popup and early/loading behavior, the latest retained
author Capicola R2 port, and selected-track/stopped keyboard ARP. Buffers remain
volatile. The current package is the switch-corrected build at
`out/runs/sketch-capi-arp-switchfix-package-20261027-01/`, SHA-256
`8880c38aac968f24dc742cbb5e9ed398223214d465d127fba7f804ac5d5b5e8a`.
The earlier combined package omitted the binary switch renderer. The correction
changes only two CPU bytes; its DSP matches the earlier package exactly.

The earlier package passed 386 tests, exact rebuilds, audio oracle/routing,
native decompression, SINE replay, coupled Sketch capture/save/retry and native
ARP panel checks. The switch correction separately passed 141 focused tests,
exact repeat, CPU/depacker checks and native callback initialization with the
old knob as a negative control. Full audio/workflow checks were not rerun for
that two-byte correction. ONESHOT-only BUF cleanup qualification remains.
No hardware upload or physical validation of this combined package; R8 below
remains the accepted experimental checkpoint. [Capicola's guide](CAPICOLA.md)
identifies the source and STRETCH-only scope.

[Repository cleanup on 2026-10-28](REPO-CLEANUP-2026-10-28.md) separates historical
reports and tests and removes obsolete OS packaging choices; it does not promote
a new firmware or hardware checkpoint.

## BUF startup refinement — 2026-10-27

Optional managed-profile switches add visible LOADING rows/status and try safe
slot reservation before the ordinary project sample-load loop. The original
loader order, publication fence, DSP and RAM reservation are preserved. See
[behavior and build recipe](SKETCH-MANAGED-RESULTS.md#startup-visibility-and-early-reservation--2026-10-27).
265 scoped tests, the source-matched native capture/FREEZE/save workflow and
pending-to-ready panel checks passed. The local package is in
`out/runs/buf-loading-os-package-20261027-01/`. This remains separate from the
accepted hardware checkpoint.

## Optional Sketch assignment popup — 2026-10-27

The managed builder accepts `--assign-popup` for a stock-style assignment dialog
after successful BUF recording. TRG 1–16 chooses a sample track; NO leaves track
assignments unchanged. It assigns the recorded live BUF and does not save or
freeze it. The default managed build remains byte-exact. See
[implementation, reproduction and validation](SKETCH-ASSIGN-POPUP.md). This is
an optional local experiment, not a new hardware-qualified checkpoint.

## Managed Sketch — local successor to R14, 2026-10-26

The opt-in [managed buffer profile](SKETCH-MANAGED-RESULTS.md) adds independent
per-BUF preferences, normal-recorder setting restoration, capacity admission and
compact status feedback. It retains the committed recorder, generation/FREEZE,
reader protection and explicit Sketchbook export paths. Project persistence is
explicitly excluded; unsaved takes and preferences are volatile. See the linked
result for exact tests, reproduction and hardware limitations. R8 remains the
accepted hardware checkpoint below; this profile does not change that claim.

## Sketch/BUF R8 — accepted experimental checkpoint, 2026-10-25

The user reports the R8 SONG recording indicator works on hardware, following
working R7 navigation/BAR controls and the R6 repeat-recording repair. There is
no installed-hash readback and no claim of exhaustive hardware validation.

The current source is consolidated under one reproducible
[Sketch/BUF checkpoint](SKETCH-BUF-CHECKPOINT.md). Its profile is
`profiles/sketch-buf-r8.json`; the build wrapper requires byte-exact R8 MAIN/DSP.
The [compact record](checkpoints/SKETCH-BUF-R8.json) preserves native LED/capture
checks and artifact hashes. Firmware and private test inputs remain local.

Working behavior includes fixed H124–H127, SRC aliases before A00, independent
NORMAL defaults, BAR/NOW during playback, immediate stopped recording, global
FUNC+SONG from ordinary pages, all sixteen trig exits, automatic publication,
R6 cleanup, snapshot COPY/PASTE and capture-only red SONG output. See the guide
for the full controls and ownership rules.

Known boundaries remain ONESHOT reader qualification, finite LEN16/32/64 and the
ten-second bound, volatile buffers/clipboard, the existing snapshot budget,
modeled recorder input and physical timing/audio gaps. The extra R7 keyboard and
sample-browser checks remain unqualified. No new pool, persistence, preview or
full-OS Flex replacement was included in this cleanup.

## Working policy

Start with the task/source/check map in [docs/README.md](README.md). For firmware
work, use `labctl doctor` and the smallest relevant suite; add `sketch-build`
when emitted code, placement, profiles or packaging change. Rebuild the affected
package when firmware changes. Documentation or test organization alone needs
no fresh OS or long audio/capture run. A behavior change needs its own targeted
validation; do not repeat passing checks without a reason.
Older Arp, Capicola, Plaits, Flex and native-emulator source work is checkpointed
separately from the R8 integration; no new hardware claims are added for it.

## Historical results

[STATUS-HISTORY.md](STATUS-HISTORY.md) preserves the previous chronology and its
limits. Earlier prototype directions and controls are historical. The frozen
backend proposal remains hash-pinned; the current checkpoint guide records the
later user-approved controls. Keep original stages, failed probes and known-good
packages for comparison rather than deleting them during housekeeping.
