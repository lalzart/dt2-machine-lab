# Sketchbook sample export — OS1.16

The opt-in `--sketchbook-save` profile extends Sketch/BUF R10. The ordinary R10
build remains byte-exact. No device was flashed and no changes were committed.

## R14 compact Sketch panel, 2026-10-26

The main SONG panel now shows a centered SKETCH title and six compact values:
A-D are BUF, SRC, CHAN and LEN; E/F are MON and START. The wide four-buffer
indicator strip, bottom status/shortcut text and header ARM/status graphics are
removed. BUF is a single numeric selector, matching the compact LEN layout.
The native Sketchbook list still opens with SONG then physical DOWN; its
EMPTY/READY rows, preview, filename dialog and save controls are retained.

A-F use OS1.16's original discrete-choice scaler (`0x40111b62`, configuration
`0x44d2e600`) with the view's existing per-encoder accumulator and timer. Small
pulses accumulate through the stock filter. A filtered event can change at most
one choice, including a fast turn. Saturated or unchanged input does not clear
feedback, write settings or request a redraw. Existing capture edit gates remain.
This controls response in native instruction and UART tests; physical knob feel
still requires the user's device trial.

- `out/runs/sketch-r14-ui-20261026-02`: cold-boot CPU-only recorder/Sketch/list
  captures inspected. Actual UART input leaves BUF unchanged after one small
  pulse; subsequent fast events change it by at most one, reaching BUF 2. The
  stock enum divisor and step were checked in initialized native RAM. DOWN
  opens Sketchbook and LEFT returns to the compact panel.
- `./labctl unit buf core integration`: 229 passed with the explicit Rust bridge.
  New tests execute the original stock scaler, including small motion, reversals,
  fast turns, native timer decay, boundaries and busy capture gates for A-F.
- `out/runs/sketchbook-r14-build-20261026-02`: deterministic final build; unchanged
  360,448-byte reservation, 56,645-byte payload and exact R11 DSP. The earlier
  build-01 is a superseded development artifact.
- `out/runs/sketch-r14-ui-20261026-01/preservation.json`: source snapshot confirms
  only the drawing, rotation, code classification and focused tests changed;
  backend sources are identical. Default R10 MAIN and stock Samples methods
  remain byte-exact. Ruff and `git diff --check` pass.

- `out/runs/sketchbook-r14-native-20261026-01/report.json`: final exact-build
  coupled CPU/SHARC flow passed in 376.6 seconds. Recording, freeze, replacement,
  physical arrows, naming cancellation/confirmation, nonzero modeled preview,
  both saves, duplicate refusal, disabled-readback failure and retry passed.
  Code, canaries, associations and frozen source hashes remain intact. OLED
  captures were inspected; the main panel has no footer or header toggle.
- `out/runs/sketchbook-r14-reload-20261026-01/reload.json`: independent original
  stock loader passed, matching both saved native files and both PCM channels.
- `out/runs/sketchbook-r14-package-20261026-01/manifest.json`: verified local
  container, unchanged DSP, exact build/native MAIN and protected sections.

Firmware: `EXPERIMENTAL_SKETCH_BUF_R14_COMPACT_UI_OS1.16.syx`.
SYX SHA-256: `510445f1e452dcae8a68330a691a1c7ead8229fd76e13da7b1b507fa48de124f`.
MAIN SHA-256: `0f85c967ff1034e3e22ac0d9134fd33e89d198e0df9693076a6d924493adfd1d`.
No hardware upload or physical knob-feel claim is made.

## R13 recorder-style panel and physical arrows, 2026-10-26

The user reports that R12's SONG > DOWN does not open Sketchbook on hardware.
R12 incorrectly used code 13 (physical LEFT) for DOWN, while its test repeated
that numeric assumption. The authenticated OS1.16 panel-name table at
`0x4020aba8` identifies UP=11, LEFT=13, DOWN=14 and RIGHT=15. R13 checks those
names during the build. Its native probe separately resolves the physical
names from MAIN and tests LEFT refusal, DOWN entry, UP/DOWN selection and LEFT
return, as well as NO and naming-dialog release ownership.

The SONG panel now borrows the recorder's value/label fonts, ARM/status bitmap,
four-column parameter layout and arrow drawing primitive. A-D remain BUF, SRC,
CHAN and LEN; E/F remain MON and START. Four buffer indicators show readiness
and underline the selected BUF. A separate status line preserves the existing
capture/freeze feedback. The bottom DOWN arrow points to Sketchbook; YES retains
the existing frozen-take display. Filled buffer indicators mean READY; outlines
mean EMPTY. The native Samples screens, filenames and `/Sketchbook` destination
are unchanged.

The change is CPU UI only. DSP, capture/loading/freezing/retirement/readback,
preview and file-writer sources are unchanged. The reservation remains 360,448
bytes. `lab/sketch_panel.py` uses a checked unused interval in the existing
Sketch arena; its instructions are explicitly classified and relocated as code.

- `out/runs/sketch-r13-ui-20261026-03`: final CPU-only cold-boot visual observer,
  zero DSPI2 peer, physical names read from MAIN; original recorder, settled
  Sketch panel, DOWN entry and LEFT return captured. PNGs inspected, including
  the long stopped-recording hint and caption spacing. This is UI evidence.
- `out/runs/sketchbook-r13-build-20261026-02`: deterministic final build.
- `out/runs/sketchbook-r13-native-20261026-01`: full capture/freeze/replacement,
  physical arrows, naming, preview, save, collision and failed-transfer retry
  passed before the final two-pixel caption spacing adjustment.

- `out/runs/sketchbook-r13-native-20261026-02/report.json`: final exact-build
  coupled CPU/SHARC flow passed, including physical arrows, native filename
  editor/cancellation, audition, both saves, duplicate refusal, disabled DSP
  readback failure and successful retry. Code, canaries and associations remain
  intact. Final panel/list/name-editor OLED frames were inspected.
- `out/runs/sketchbook-r13-reload-20261026-01/reload.json`: independent stock
  loader passed; both saved native files and both PCM channels match exactly.
- `./labctl unit buf core integration`: 226 passed with the explicit Rust bridge;
  touched-source Ruff and `git diff --check` pass. The source/backend preservation
  and default R10 equality checks are in
  `out/runs/sketch-r13-ui-20261026-01/preservation.json`.
- `out/runs/sketchbook-r13-package-20261026-01/manifest.json`: local package,
  decompression and staging checks passed. Original Samples methods and the R11
  DSP remain byte-exact. No R13 hardware upload or physical timing claim is made.

Firmware: `EXPERIMENTAL_SKETCH_BUF_R13_RECORDER_UI_OS1.16.syx`.
SYX SHA-256: `8342af71f261e9884f6fb8ad94a2e809d737af8de74e7ce387cc202d50b15ee2`.
MAIN SHA-256: `9b3329e91d234b8087610dd885ffa40eb18e93ba32107c98332b0d2064121bdc`.

## R12 SONG-page UI, 2026-10-25

The user reports R11 saving works on their device. R12 moves that working
backend's frontend out of Samples and into Sketch, following their requested
alternative. It removes the four stock UI hooks and uses only Sketch's existing
view lifetime. The list has an inverted selection bar, four visible rows and a
position/total header. YES opens naming on release; the opening key cannot also
accept the default name. Canceling naming returns to the list without a save.

- `out/runs/sketchbook-r12-build-20261025-03`: deterministic final build, exact
  CPU match to the native run, unchanged R11 DSP and 360,448-byte reservation.
- `out/runs/sketchbook-r12-native-20261025-02/report.json`: passed the original
  recording/freeze/replacement/preview/save/failure flow, plus original Samples,
  SONG > DOWN, list back/reopen, idle naming dialog, cancel and explicit confirm.
  Captured OLED frames and PNGs were visually inspected.
- `out/runs/sketchbook-r12-reload-20261025-01/reload.json`: passed; both native
  files and both reloaded PCM channels match exactly through the stock loader.
- `./labctl unit buf core integration`: 225 passed with the explicit Rust bridge.
  Ruff and `git diff --check` pass. The source-preservation record is
  `out/runs/sketchbook-ui-r12-20261025-01/preservation.json`.
- The earlier native-01 run saved correctly but exposed the naming-key issue
  in its OLED capture; it is superseded by native-02. Earlier builds are retained.

Local package:
`out/runs/sketchbook-r12-package-20261025-01/EXPERIMENTAL_SKETCH_BUF_R12_SONG_SKETCHBOOK_OS1.16.syx`.
SYX SHA-256: `2117ae55e7953f611fccb4d96668c2236a2f4466bee99f85f60c94c9049e013b`.
MAIN SHA-256: `97dfc19f7156ad945109138402f57264e883c786b1f5da005efc4ebb1d117ff7`.
DSP SHA-256: `37270ca2f528a6dae7d0bd8aa8f463d21e523c1e82217fa12717d849f1f568ae`.
Container decompression/staging checks pass. R12 has not been uploaded or tested
on hardware; the original Samples methods are byte-exact to OS1.16.

## Controls

R12 moves the export list to Sketch, as requested after the successful R11
device test. Press SONG, then DOWN to open Sketchbook. The first four rows show
BUF 1–4 as EMPTY/READY. Ready freezes follow, with their H slots. UP/DOWN or the
data encoder selects a row. The header shows the selected row and total count.

- YES opens the original filename editor and saves to `/Sketchbook/<name>`.
- RIGHT downloads an audition snapshot and starts the original preview player.
- NO or LEFT returns to Sketch; a second NO leaves Sketch. STOP/NO cancel a
  pending audition while preserving stock key delivery.

The Samples source chooser, its draw/key/encoder methods, and the base View
destructor are original firmware bytes again. The old chooser encodes its two
sources as a Boolean, rather than offering a row-registration interface. Its
RAM and +Drive lists also own filesystem-specific operations. The requested
separate SONG-page list avoids adapting those interfaces for volatile takes.
The earlier plan's Samples UI mapping and R11 screenshots describe the previous
frontend; the readback, writer, preview, filename editor and DSP are unchanged.

Existing filenames are refused. Empty/stale/busy sources and failed saves show a
message. Save does not change BUF, freeze, project references or track assignment.
Saved files are ordinary +Drive samples, browsable inside the Sketchbook folder.
There is no automatic project or buffer restoration in this version.

## Storage and lifetime

Accepted BUF/FREEZE audio remains on the DSP. Before the temporary recorder CPU
source is freed, export retains only its 64-byte native header and 16-byte trailer.
A native request binds the generation, epoch, private allocation and exact DSP
header. Checksummed replies carry at most 224 PCM bytes in an added DSPI2 tail;
the original 2748-byte prefix is preserved. The 3008-byte frame stays within the
original driver's 3008-byte cap and existing DMA-ring spacing.

Saving reconstructs through a 4096-byte CPU buffer and the existing exclusive
native file writer, including durable hash/length verification. A save lease
blocks conflicting mutations until an explicit DSP CLOSE acknowledgement revokes
the reader. Lost acknowledgement retains the lease rather than allowing reuse.

Audition separately allocates one temporary CPU native-file snapshot, bounded to
1,920,080 bytes. The original preview reader owns it through asynchronous reads
and frees it at close. Audition creates no disk file. Saving never uses this full
file allocation. The filename closure binds the original token; metadata-seat
reuse cannot redirect an in-progress naming dialog.

## Evidence

- `out/runs/sketchbook-persistence-20261025-01/native-05`: native CPU/SHARC capture A,
  freeze, replacement B, export of both after CPU-source release, duplicate refusal,
  unchanged associations and matching reader-close acknowledgements.
- `.../reload-draft/reload.json`: independent stock CPU cold boot/loader; both saved
  native files and both channels of reloaded PCM matched exactly.
- `.../native-06`: native three-source Samples menu, empty warning, frozen list,
  nonzero modeled preview output, asynchronous preview-source cleanup, no audition
  disk writes, original filename dialog and explicit saves. OLED frames inspected.
- `.../native-07`: the same flow plus disabled DSP data-emitter failure and a
  successful retry with the same filename, proving partial-file cleanup.
- `.../dsp-check-05`: native SHARC mono/stereo, odd offsets, chunk boundaries,
  stale request/header refusal, preserved stock prefix and CLOSE with data disabled.
- Focused Rust ColdFire fixtures cover metadata capture, placed-address arithmetic,
  packet corruption/order/identity/count, bounded native-file reads, name validation,
  immutable naming, stock preview source lifetime and null/unrelated dispatch.

R11 backend validation (preserved):

- `.../native-08/report.json`: passed, including STOP during audition download,
  real preview, named save, duplicate refusal, disabled data emission, clean
  failure and successful retry. Unchanged source/track/snapshot associations.
- `out/runs/sketchbook-r11-reload-20261025-02/reload.json`: passed; exact native
  files and both channels through an independent, cold-booted stock CPU loader.
  Sketchbook contains only `Sketch`, `Buffer-B` and the successful `NoReadback`
  retry; the failed transfer left no extra file.
- `./labctl unit buf core integration`: 222 passed with the explicit Rust bridge.
- `out/runs/20261025T123817Z-test-8c3fdd63/manifest.json`: SINE replay passed.
  The earlier source-drift run was retained as a failure, not counted as passing.
- Final touched-source Ruff and `git diff --check`: passed. Pinned dependencies
  and unrelated inherited files remain unchanged.
- `out/runs/sketchbook-r11-build-20261025-03`: deterministic final build,
  byte-identical MAIN/DSP to the tested native-08 pair. Independent DSP boot-stream
  checks and container decompression/staging checks passed.
- `out/runs/sketchbook-r11-package-20261025-01/manifest.json`: local experimental
  package identities and links to the native/reload reports. No hardware upload.

Firmware: `EXPERIMENTAL_SKETCH_BUF_R11_SKETCHBOOK_OS1.16.syx`.
SHA-256: `82707c08995b74ab76537ff612fb31bbdb045890ad1b3b56b863db30bc4d3fff`.

The host supplies modeled recorder PCM, card sectors and peripheral cadence.
Host peeks are comparisons, never the source of successful readback replies or
job completion. Prepared SEC reset values and the preserved native boot adapter
remain explicit harness inputs. Mono is covered by direct target-instruction
fixtures; the full capture/save/preview flow uses stereo input.

Physical clock/DMA/cache timing, listening, drive-full/power-loss behavior and
installation remain unverified. The historical Unicorn Flex/retirement fixtures
remain limited by the documented host first-map SIGILL; passing Rust fixtures
and stock reload do not turn those earlier suites into passing checks.

## Reproduce

Use the configured Python 3.12, pinned dependencies and a fresh ignored run.
`scripts/check-sketchbook-save.py --help` lists the explicit R10 card/panel spec,
readback build, zero-execution DSP inputs, clean native upstream and preserved
native boot adapter inputs. `scripts/check-sketchbook-reload.py --help` describes
the separate stock reload, which materializes a private copy of the card overlay.

Build with `scripts/build-sketch-device.py` and the R10 flags
`--arm-diagnostics --clock-fix --buf-selector --performance-controls
--navigation-fixes --fixed-buf-slots --startup-capture --copy-shortcuts
--stopped-recording --recording-led --monitor-labels --freeze-h-slots`, adding
`--sketchbook-save`. Nothing is sent to hardware by these commands.
