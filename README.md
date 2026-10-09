# Digitakt II machine lab

Local source, builds and repeatable offline tests for custom Digitakt II
machines. The first machine is **SINE**, a fixed 440 Hz, 250 ms oscillator
on track 1 under OS 1.16. The source runs as new SHARC instructions.

A separate [SINE controls experiment](docs/SINE-CONTROLS.md) connects TUNE,
LEN and LEV and checks stored parameter locks through real step previews.

The [Plaits VA experiment](docs/PLAITS-VA.md) ports one original Plaits engine
to C99, compares it with upstream C++, executes it as compiled SHARC code,
and renders through the prepared DTII voice hook. Its separate repeat commands
and remaining control/timing gaps are documented there.

The optional [Plaits resource experiment](docs/PLAITS-OPTIMIZATION.md) compares
the reference with MAIN-only rendering and safe sharing between matching lanes.
It retains exact audio comparisons and reports emulator instruction savings.

The [resource monitor](docs/RESOURCE-MONITOR.md) imports saved DSP and memory
records into a local diagnostic screen. The [stock OS 1.16 baseline](docs/STOCK-RESOURCE-BASELINE.md)
compares six stock pad/settings workloads, installed-hook overhead and separate
active SINE/Plaits clips. These report emulator work and paused heap snapshots;
physical CPU/DSP utilization remains unmeasured.

The [three-model Plaits prototype](docs/PLAITS-TRIO.md) adds two-operator FM
and analog bass drum beside VA. A dedicated MODEL control recalls engines
through real stored-lock CPU captures and prepared SHARC replay. Its repeat
commands, compiler adaptations and measured instruction costs are documented.

The [six-voice Plaits bank](docs/PLAITS-BANK.md) adds waveshaping/wavefolding,
harmonic additive synthesis and granular formants as MODEL 3–5, preserving the
original VA/FM/BD models. It uses the same prepared emulator integration.

The [Plaits macro controls experiment](docs/PLAITS-CONTROLS.md) gives that bank
dedicated HARM/TIMB/MORP controls, continuous macro updates and a repeatable
panel-lock capture and buffered audio audition.

The [R3 integration](docs/PLAITS-INTEGRATION-R3-RESULTS.md) adds millisecond
duration, named models, macro LFO destinations and a track-1 selection guard.
It is a separate local build with focused CPU, panel and compiled DSP checks.

The [pattern lab](docs/PATTERN-LAB.md) connects the firmware's normal sequencer
clock and checks a 16-step edit/PLAY/stop/edit/restart workflow for the stock
sampler and Plaits. It captures the actual performance for buffered WAV replay.

[Upload preparation](docs/UPLOAD-PREFLIGHT.md) records the stock 1.16 upgrade
and recovery route, the checked custom container, and remaining hardware gates.

The [Flex sampling prototype](docs/FLEX-LITE-UI-RESULTS.md) adds a remembered
destination to the original recorder: record, stop, trim, then USE a temporary
RAM sample. It supports modeled WAV input and buffered ONESHOT audition through
`python3 scripts/try-flex-lite.py` (legacy command name). This is a host-side
emulator adapter, not an on-device machine or an uploadable firmware patch.
Its recorder service and temporary sample source still depend on Python.

The [native Flex implementation](docs/FLEX-NATIVE.md) now builds the recorder
workflow as ColdFire device instructions, with automatic sample persistence on
project save. Native UI and original project save/stock reload checks are separate
from the earlier Python prototype. A local experimental Plaits R3 + Flex package
is available. After USE, open the recorder and press **FUNC + RECORD** while
idle to name and save the selected track's Flex sample to +Drive; NO cancels.
The latest package also includes the mono-flag correction for the photographed
hardware USE error. Native naming, storage and project reload checks pass;
hardware confirmation remains pending. See the native notes for results and
current limitations.

The active [Capicola direction](docs/CAPICOLA-STRETCH-REPLACEMENT.md) replaces
the DSP behind the existing **STRETCH** machine, retaining its selector,
controls and locks. The [R3 playback implementation](docs/CAPICOLA-STRETCH-R3-RESULTS.md)
adds live PLAY and STRT/LEN edits with short crossfades, native completion,
and modeled master/DAC-ring checks. Sixteen distinct mono banks and thirty-two
reader lanes retain the existing 8 MiB budget and stock fallback under pressure.
Host comparisons, native playback, 138 source tests and SINE pass. Simultaneous
edits add significant emulator work; physical timing, full playhead/progress
bookkeeping, runtime ownership and hardware validation remain open.
The [combined firmware build](docs/COMBINED-FIRMWARE-RESULTS.md) packages this
STRETCH replacement with Plaits R3 and the latest managed streaming Flex.
It is a local experimental OS 1.16 SYX, with build/container, separate emulator
startup and regression checks; it has not been sent to hardware.
The [R2 multiple-bank work](docs/CAPICOLA-STRETCH-R2-RESULTS.md) and
[R1 replacement](docs/CAPICOLA-STRETCH-R1-RESULTS.md) are preserved.
Separate CAPICOLA selector/RATE work is superseded.

The preserved [Capicola integration prototype](docs/CAPICOLA-CONTROLS-RESULTS.md) has a
track-1 selector, pitch/rate/level controls and automatic mono sample preparation
in the OS1.16 emulator. Captured CPU sample transfers and triggers produce
native DSP voice output matching the host reference. Input remains capped at
12 seconds; one bank uses an 8 MiB reservation from the sample pool. Preparation
currently takes about twice the sample duration and needs a later trigger to
start playback. Automatic readiness refresh, project persistence, full memory ownership and
physical timing remain open; there is no hardware-ready Capicola package.
The optional [reserved-state build](docs/CAPICOLA-RESIDENT-STATE-RESULTS.md) now
places working data and stacks inside that existing reservation, with native
startup, reload and compatibility checks. Instruction-code ownership in L2
and physical memory latency still need validation.
The new [selection-preparation candidate](docs/CAPICOLA-SELECTION-PREP-RESULTS.md)
starts work when an eligible sample is selected, before the first trigger, and
exposes native progress and rejection status. The optional
[feedback build](docs/CAPICOLA-FEEDBACK-RESULTS.md) now shows preparation ranges
and READY when SRC opens, using the existing DSP reply. Native SPI return and
buffered CPU display checks pass; automatic caption refresh remains pending.

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
python3 -B -m unittest discover -s tests -v
```

| Command | Result |
| --- | --- |
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
- `tests/`: source-only harness tests and a hash-only private-fixture manifest.
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

Keep a known passing run, change source, then build/render and run the replay
suite. The suite intentionally detects changed baseline images/PCM; intentional
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
