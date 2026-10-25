# Current status

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

Use `labctl doctor`, scoped `labctl unit buf` / `core` checks and a fresh
checkpoint rebuild. Do not rerun long audio/capture suites for documentation or
organization alone. A behavior change needs its own targeted validation.
Older Arp, Capicola, Plaits, Flex and native-emulator source work is checkpointed
separately from the R8 integration; no new hardware claims are added for it.

## Historical results

[STATUS-HISTORY.md](STATUS-HISTORY.md) preserves the previous chronology and its
limits. Earlier prototype directions and controls are historical. The frozen
backend proposal remains hash-pinned; the current checkpoint guide records the
later user-approved controls. Keep original stages, failed probes and known-good
packages for comparison rather than deleting them during housekeeping.
