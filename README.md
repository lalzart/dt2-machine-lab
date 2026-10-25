# Digitakt II machine lab

This lab develops Digitakt II OS 1.16 emulator experiments. Start with the
[feature guide](docs/FEATURES.md) and [testing guide](docs/TESTING.md).

## BUF performance buffers

The [BUF workflow contract](BUF-WORKFLOW-CONTRACT.md) is the canonical product
direction: four reusable global buffers, publication without track assignment,
immutable generations and selectable FREEZE snapshots. See the
[alignment audit and results](docs/BUF-WORKFLOW-ALIGNMENT.md).

The [continuous recording milestone](docs/BUF-CONTINUOUS.md) captures 13
consecutive publications during playback, 11 native releases and 10 extent
reuses, with stable DSP and CPU memory. The capped run remains failed after a
test-only encoder assertion stopped its fourteenth capture; saved-publication
ONESHOT/REPITCH playback comparisons pass. The all-ONESHOT retirement guard
remains unchanged.

The current native CPU workflow supports an empty BUF, selection on multiple
tracks, next-bar recording into global recorder DEST and automatic publication
while performance edits continue. Publication preserves every track assignment.
**SAMPLING+YES** and **SAMPLING + push encoder C** remain provisional record and
FREEZE frontends. Saving and project persistence remain separate work.

The [native duration extension](docs/BUF-MULTIBAR.md) admits R.LEN 16/32/64 steps
(one/two/four bars) with the normal 16-step clock and existing ten-second cap.
Other lengths/MAX explicitly refuse. Recording has no all-track ONESHOT requirement.
ONESHOT is the initially proven playback path, and mixed-machine DSP runtime
support, conservative retirement guards, target placement and hardware remain
open. [Earlier next-bar results](docs/BUF-NEXT-BAR-RESULTS.md) retain the seed-take
and assigning prototype's evidence; they are not the product specification.

## Sketch UI prototype

The user reports the clock-correction firmware now works on their device.
The [selector and startup investigation](docs/BUF-SELECTOR-AND-STARTUP.md) traces
the remaining loader wait and the native encoder-D list. Empty BUFs already
select through their backing slots; four aliases before A00 are the requested
next UI. Changing slot addresses alone does not isolate the shared allocator.
This investigation leaves the working firmware unchanged.

The [clock correction candidate](docs/SKETCH-CLOCK-CORRECTION.md) follows the
user's report that startup loading clears and ARM then reaches `REF CLOCK 0`.
It uses stock transport semantics and normal16 pattern fields, adds specific
clock refusals and passive `WAIT SAMPLES`, and passes a focused native next-bar
capture/publication. Its physical clock cause and behavior remain unconfirmed.

The [startup sample-operation diagnostic](docs/SKETCH-STARTUP-SAMPLE-DIAGNOSTIC.md)
prioritizes the first post-boot `BUSY FREEZE 1` refusal. It identifies a guarded
stock load/unload/clear operation where possible, preserving the busy guard and
excluding the pending clock correction. The physical cause remains unconfirmed.

The opt-in [ARM diagnostic package](docs/SKETCH-ARM-DIAGNOSTIC.md) identifies the
first blocking check behind the user's hardware BUSY/REFUSED report. It retains
all recording guards and leaves the original experimental package intact.

A local [Sketch/BUF experimental OS1.16 package](docs/SKETCH-EXPERIMENTAL-PACKAGE.md)
now passes exact-package integrity, native CPU upload/backpressure and complete
container application-startup checks. It reuses the identical native recorder
workflow bytes, runs no new captures and remains hardware-unqualified.

[Sketch](docs/SKETCH-UI.md) is a separate opt-in native menu over BUF with
SONG tap navigation, dry FUNC+SONG ARM and dry held-SONG FREEZE. It remembers
one BUF selection independently of recorder DEST=NORMAL. No jobs, preview or
persistence are attached to those shortcuts.

The optional [real ARM profile](docs/SKETCH-ARM.md) connects FUNC+SONG to the
existing next-bar recorder and publication service using Sketch's selected BUF,
while preserving normal recorder DEST. Held SONG remains dry in this profile.
Its live feedback follows the admitted BUF through waiting, recording, loading,
publication or cancellation, independently of later BUF selection.

The additional [FREEZE profile](docs/SKETCH-FREEZE.md) connects held SONG to a
generation-specific snapshot of Sketch's selected BUF. Enable ARM and FREEZE
together for the complete opt-in Sketch control mapping. Default controls stay dry.

[Combined DSP validation](docs/SKETCH-VALIDATION.md) passes two native captures,
held-SONG FREEZE and exact stock-file voice PCM comparisons. Publication still
takes about 196–197 ms after capture in the model; physical timing and final
output remain unverified. The separate [device placement experiment](docs/SKETCH-DEVICE-PLACEMENT.md)
adds a bounded DDR layout and local startup checks while preserving the existing
Flex build profiles. It is not a hardware-ready package.

[Device-address validation](docs/SKETCH-RELOCATED-VALIDATION.md) now passes the
prepared coupled two-take/FREEZE workflow using those exact binaries, with intact
code/canaries, no old-arena accesses and exact parity with the earlier layout.
Paired cold startup and physical device memory behavior remain unverified.

The [DSP boot-memory correction](docs/SKETCH-DSP-BOOT-MEMORY.md) removes a
boot-kernel workspace overlap that prepared fixtures bypassed. The current
device recipe relocates only the retirement-gate state, rejects boot-area
writes and preserves the ordinary emulator DSP byte-for-byte. Bounded DSP
startup and saved-page native seal/refusal controls pass with no new recordings.
The `-07` and `-09` images are retained as emulator/application evidence.
The subsequent [boot-stream/upload audit](docs/SKETCH-BOOT-UPLOAD.md) found and
corrected additional FINAL ordering, alignment and FIRST-span defects. Use a
fresh build from the current device recipe for ongoing local preparation.
That audit's sealed build is `sketch-device-build-20261023-13`; its
[upload evidence](out/runs/sketch-rom-upload-20261023-07/verification.json)
records the remaining ROM, SPI FIFO and container-startup limits.

[Coupled application startup](docs/SKETCH-COLD-STARTUP.md) now passes stock and
the corrected `-09` build from CPU reset and DSP loader application entry,
with live native control and card sample loading. Sketch renders after startup;
reset clearing/code/canaries, a measured disconnected-DSP control, 145 BUF tests
and final-source SINE pass without new recordings. The later boot-stream audit
adds native CPU upload/backpressure checks under a modeled ready line. Actual
ROM execution, SPI FIFO/tail acceptance and physical startup remain unverified.

The [first native migration slice](docs/NATIVE-BUF-MIGRATION.md) now loads the
complete candidate container through an authenticated-reference constructor,
runs paired application startup and renders Sketch. Saved A/B/FREEZE voice PCM
matches the old runtime exactly over 96 blocks. The reply/final-output differences
are now explained by corrected upstream SIMD semantics. The
[native recorder connection](docs/NATIVE-BUF-RECORDING.md) passes a two-take/FREEZE
workflow, active cancellation and independent stock-file final-output checks.
It remains opt-in, with modeled stereo recorder input and unchanged lab pins.

## Flex recording and saving

Flex is the existing RAM-take recording/save workflow. Its current R5 save flow
uses the stock filename editor, a visible A-H RAM-bank chooser and a slot preview;
Save/Discard and project persistence have their own code and checks. See
[Flex R5 results](docs/FLEX-BANK-SAVE-RESULTS.md).

BUF and Flex have separate adapters and test suites. Existing all-feature builds
contain Flex; BUF has separate adapters and an isolated device profile. Their shared recorder
helpers do not combine the two features.

For a future combined OS, BUF/Sketch replaces this previous Flex implementation;
the user does not want both included. Existing Flex profiles remain preserved
as reference. Current experimental packaging uses the isolated Sketch/BUF profile.

## Other experiments and history

[Arp](docs/ANY-TRACK-FEATURES-RESULTS.md), Plaits and
[Capicola](docs/CAPICOLA-REDDIT-BOOT-FIX-RESULTS.md) remain available independently.
Their detailed suites run when selected. The [recorded milestone summaries](docs/EXPERIMENT-HISTORY.md)
retain the earlier work and its evidence without making every old experiment
part of routine BUF verification.

Start with [STATUS](docs/STATUS.md), [integration findings](docs/INTEGRATION.md),
and the [development roadmap](docs/DEVELOPMENT.md). [AGENTS.md](AGENTS.md)
contains the short development instructions.

## Everyday commands

From this directory:

```sh
./labctl doctor
./labctl build sine
./labctl render sine
./labctl test sine --replay
./labctl profile sine
./labctl unit buf
```

| Command | Result |
| --- | --- |
| `unit` / `unit buf` | Runs the native BUF and shared recorder unit tests. Does not run Capicola, Arp or older BUF models. |
| `unit flex` | Runs existing Flex and shared recorder tests. |
| `unit all` | Explicit full repository regression; see [suite selection](docs/TESTING.md). |
| `doctor` | Checks dependency commits, clean dependency trees, Python package versions, patched Unicorn binary, tool binaries and every private fixture hash. |
| `build sine` | Builds CPU MAIN and SHARC BLOB overrides using expected-byte guards; no firmware container or boot. |
| `render sine` | Rebuilds and renders the saved SINE control stream; checks frequency, envelope and silence. About 40–50 seconds for one second of audio on the initial interpreter build. |
| `test sine --replay` | Runs the complete prepared-fixture regression suite, including the original image/PCM hashes, exact repeat, stock isolation, clone parity, disabled-hook control and retrigger/switch behavior. Allow several minutes. |
| `profile sine` | Renders the same bounded fixture and records per-block retired instructions and host timing distributions. Hardware CPU/DSP load fields remain unset. |

Each build/render/test gets a new `out/runs/<time>-<command>-<id>/` directory.
It contains `manifest.json`, `run.log`, candidate images and relevant outputs.
A successful audio run produces `sine-440.wav`. `out/latest.json` points to
the latest successful run. Failed and timed-out runs retain a failure report;
they do not replace that pointer. Verification remains active under Python
`-O`. A source or fixture change during a run prevents a passing result.

Earlier stages remain documented: [pool reservation](docs/CAPICOLA-OWNED-MEMORY-RESULTS.md),
[native preparation](docs/CAPICOLA-NATIVE-PREP-RESULTS.md),
[R1 reader integration](docs/CAPICOLA-INTEGRATION-R1-RESULTS.md), and
[twelve-second capacity](docs/CAPICOLA-TWELVE-SECONDS-RESULTS.md).
Their open-item lists describe those historical stages; current integration
results are linked above.

## Layout and dependencies

- `machines/sine/`: assembly, linker placement, and the machine definition.
- `machines/sine-controls/`: experimental pitch, duration and level wiring.
- `machines/plaits-va/`: pinned-source C99 translation and experimental wrappers.
- `machines/plaits-trio/`: VA/FM/BD source port, control map and upstream oracle.
- `machines/plaits-bank/`: six-model extension, generated source and upstream oracle.
- `machines/plaits-controls/`: dedicated macro control map and continuous adapter.
- `profiles/dt2-1.16/`: stock image hashes and version-specific integration data.
- `lab/`: lab-owned CPU build, DSP replay, validation, and reporting adapters.
- `tests/`: feature-scoped unit suites in `suites.json`, shared native BUF fixtures,
  and a hash-only private-fixture manifest. See [testing guide](docs/TESTING.md).
- `deps.lock.json`: exact DigiKit, Selache, Unicorn and Python dependency pins.
- `.deps/`: ignored, clean dependency checkouts; no machine source lives here.
- `.local/`: ignored local configuration and the private replay fixture.
- `out/`: ignored builds, database cache, images, captures, audio and reports.

The current Mac is configured. `labctl` selects the Python executable recorded
in `.local/config.json`; it currently reuses the original validated DigiKit
Python environment. DigiKit/Selache source checkouts and the replay fixture
are separate copies in this lab. No original project files were removed.

The native library/state and Selache executable fingerprints identify the
initial macOS arm64 fixture. A rebuilt or different-platform toolchain needs
its own validated fixture. A matching source revision alone does not prove
that an imported native state is compatible with a library.

## Recreate this setup from the preserved experiment

With the original workspace still available, run:

```sh
python3 scripts/import-workspace.py "/path/to/Digitect firmware research project"
./labctl doctor
./labctl test sine --replay
```

The importer checks the recorded input hashes, creates independent dependency
clones at the pinned revisions, copies the small private replay fixture and
tools, and records the Python environment explicitly. Re-running it checks
existing files; it refuses to overwrite changed inputs or configuration.
It does not copy the 4 GB virtual drive or CPU snapshots.

This is a reproducible **prepared-fixture replay**, not yet a rebuild from
only the original `.syx`. The next milestone is a fixture generator covering
patched CPU and DSP initialization, sample/card preparation, and panel capture
in one run. There is deliberately no `--clean` command claiming that today.

## Working on a machine

Keep a known passing run and run the relevant [unit suite](docs/TESTING.md)
after source changes. Build/render and replay when DSP or adapter behavior changes.
The replay suite intentionally detects changed baseline images/PCM; intentional
algorithm changes need reviewed expectations and signal checks. Do not make a
failing comparison pass by regenerating its expected hash automatically.

The fixed SINE baseline has no controls; the separate SINE controls variant
connects pitch, duration and level. Plaits VA adds a compiled engine experiment.
Sample-free startup, downstream processing, more tracks and physical resource
measurements remain open. See [DEVELOPMENT](docs/DEVELOPMENT.md).

Elekloader is recorded as an optional future integration in
[ECOSYSTEM](docs/ECOSYSTEM.md). It is not a dependency of the current DSP test.

Firmware and derived files stay private and ignored. This repository builds
emulator overrides, local experimental containers and bounded audio captures.
Modeled final-output checks, physical timing and hardware operation remain
separate observations.

The [arp emulator prototype](docs/ARP-PROJECT-LOAD-RESULTS.md) provides G OFF/UP/ORDER/RANDOM, ordinary note recording and authenticated project-menu recall. Its local native CPU, persistence, exact musical parity and regression checks pass; physical integration remains separate.

The [native stock arp build](docs/ARP-STOCK-FIRMWARE-RESULTS.md) now packages
G OFF/UP/ORDER/RANDOM, clocking and native recorded-project mode recall on
stock OS 1.16. It is an experimental track-1, fixed-102-BPM build; emulator
record/save/menu-load/replay and container checks passed, but the first user
hardware trial produced no arp. The keyboard-state follow-up is documented
in the results; its physical result remains unconfirmed.

The optional [any-track all-feature build](docs/ANY-TRACK-FEATURES-RESULTS.md)
removes the fixed T1 restrictions: the keyboard arp follows the selected track
and Plaits has independent state on all tracks. It retains stopped arp and the
repaired author Capicola backend. Capicola and compatible Flex destinations
already support other tracks. See that report for exact artifacts, validation
and device-test boundaries.
