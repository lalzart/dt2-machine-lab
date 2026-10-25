# dt2-capicola

A custom OS for the **Elektron Digitakt II** that upgrades its time stretching.
It replaces the Digitakt II's native time-stretching and repitch algorithms
with an engine built on [Capicola](https://github.com/heavylight-industries/capicola),
a real-time time stretcher and pitch shifter by Heavylight Industries.

- The upgrade covers the STRETCH, REPITCH, SLICE and GRID machines.
- A new **CAPI** parameter switches each track between the upgraded engine and
  Elektron's native one, so you can always compare them or go back.
- The mod also syncs SLICE and GRID to the tempo and raises BARS to 32.

> [!WARNING]
> **This is not an Elektron product, and Elektron does not support it.**
> It replaces your instrument's operating system with a modified one. It has
> been tested on one unit by its author, and only in the ways described below.
> Building it, installing it or playing it may cause problems: crashes, freezes,
> clicks or unexpected sound. In the worst case you may have to restore the
> stock OS (see [Going back to the stock OS](#going-back-to-the-stock-os)).
> Back up your projects and samples first. You use this entirely at your own risk.

## Contents

- [Quick start](#quick-start)
- [Compatibility](#compatibility)
- [What it does](#what-it-does)
- [DSP load: native and Capicola](#dsp-load-native-and-capicola)
- [Building](#building)
- [Troubleshooting the build](#troubleshooting-the-build)
- [Installing](#installing)
- [Going back to the stock OS](#going-back-to-the-stock-os)
- [Measuring the load on your unit](#measuring-the-load-on-your-unit)
- [Tests](#tests)
- [elekloader](#elekloader)
- [Credits](#credits)
- [License](#license)

## Quick start

Download the Digitakt II OS from Elektron's support page
(`Digitakt_II_OS1.17.syx`, or the `.zip` it comes in). Then:

```sh
git clone https://github.com/hy3na-k1ng/dt2-capicola.git
cd dt2-capicola
./build.sh --stock ~/Downloads/Digitakt_II_OS1.17.syx
```

[`build.sh`](build.sh) does the rest:
- installs the tools it needs, asking before each step;
- fetches and builds the projects it depends on;
- writes the image to `out/dt2capicola_DT2_1.17.syx`.

Send that file to the Digitakt II with Elektron Transfer. See
[Building](#building) for the details and options,
[Compatibility](#compatibility) for supported systems, and
[Troubleshooting](#troubleshooting-the-build) if it stops with an error.

**What to expect the first time.** On a Mac that has never been used for
development, the script needs Apple's **Xcode command line tools** and
**Homebrew**, and offers to install each. Both ask for your password, and
together with the Rust toolchain they take 15 to 30 minutes and a few GB of
disk. None of this is needed again: later builds take about 20 seconds.

## Compatibility

### Digitakt II OS

| OS | status |
|---|---|
| **1.17** (latest) | supported; the default. Played on the instrument with the diag build |
| 1.16 | supported. The version most of the development and playing was done on |
| any other | refused: the build checks Elektron's file by hash, and stops |

Each image is built for one OS version and installed in place of it. The DSP
program is the same in 1.16 and 1.17, so the sound is the same on both.

### Computers to build on

| system | status |
|---|---|
| **macOS** (Apple silicon, Homebrew) | tested: `build.sh` from a clean clone, all tests pass |
| **Ubuntu 24.04** (x86-64) | tested: `build.sh` from a clean container, all tests pass, image byte-identical to the macOS build |
| other Debian / Ubuntu versions, and Ubuntu on ARM | expected to work (same apt packages); not tested |
| **Windows** | through WSL with Ubuntu (the Linux route); not tested. Native Windows is not supported |
| other Linux distributions | install the tools yourself (see [Building by hand](#building-by-hand)); `build.sh` then skips its install step |

- **Memory:** building needs little. The emulator tests (`--tests`) need about
  3 GB per parallel run, and pick how many to run from the free memory.
- **The diag image** can differ by a few bytes between macOS and Linux,
  because their m68k assemblers encode one instruction differently. Both
  forms do the same thing. The release image is identical on both.

## What it does

### CAPI: the engine switch

All four machines get a new parameter, **CAPI** (Capicola), on the SRC page.
It takes the empty slot after PLAY. It shows as a switch, or as words on SLICE
and GRID, and is also drawn on the SRC page's second (waveform) view.

- **OFF** (the default) plays Elektron's own machine. Its output is
  bit-for-bit the stock machine's: the tests check this for all four machines.
  Projects you already have sound the same until you turn CAPI on.
- **ON** plays the Capicola engine.

CAPI is set per track, so stock and Capicola tracks can play side by side. The
parameter is assigned MIDI CC 18. Controlling it over MIDI has not been tested.

### STRETCH

With CAPI on, STRETCH plays the sample through the Capicola engine:

- Time and pitch are independent. BARS, LEN and the tempo set the speed, and
  TUNE sets the pitch.
- TUNE uses its full range downwards. The stock machine stops at −4 semitones.
- Stereo samples play both channels in one pass, so the channels stay
  aligned.
- All PLAY modes work: forward, reverse and both loop modes. So do retrigs.

### REPITCH

With CAPI on, REPITCH plays the sample at the stock machine's varispeed rate,
so pitch follows the tempo as before. It reads the sample with Capicola's
interpolated read, at the stock machine's level.

### SLICE and GRID

On SLICE and GRID, CAPI has three settings:

| CAPI | what plays |
|---|---|
| **OFF** | Elektron's machine, unchanged |
| **REP** | the REPITCH way: the sample follows the tempo by varispeed, so pitch follows the tempo too. TUNE is hidden, because it has no effect |
| **STR** | the STRETCH way: the sample follows the tempo, and TUNE sets the pitch independently |

- **SLICE** gets a **BARS** parameter in slot 6: the length of the whole
  sample in bars, from 1 to 32. With the tempo, this sets the speed every slice
  plays at.
- **GRID** takes the length from its own GRID setting, and assumes each slice
  is a 16th note.

### BARS up to 32

On STRETCH and REPITCH, BARS now goes up to 32 instead of 8, and the picture
shows 16 and 32 bars too. This works with CAPI on or off.

### How the engine works

Capicola stretches audio with two read heads:
- an **ideal** head that moves at the stretch rate (where the music should be);
- an **actual** head that plays at the pitch.

When the actual head drifts more than 640 samples from the ideal one, the
engine splices it back with a crossfade, at a point where the audio lines up.
The original Capicola chooses splice points from a keyframe analysis of the
audio, described in the paper *[Keyframe Time Stretching via Extrema
Sampling](https://github.com/heavylight-industries/dafx26-paper)* (DAFx26).
With 16 tracks sharing one DSP, that analysis cost too much. This version keeps
Capicola's heads, splices and read, and lines splices up by comparing the
samples themselves.

The C code in [capicola_c99/](capicola_c99/) is a C99 port of Capicola's C++
core. It matches the original sample for sample, which
[capicola_c99/test/compare.cpp](capicola_c99/test/compare.cpp) checks. On top of
that port, the Digitakt-specific parts are:
- the generators in [capicola_c99/sharc/](capicola_c99/sharc/), in C and SHARC
  assembly;
- the firmware patches in [firmware/](firmware/).

## DSP load: native and Capicola

These figures were measured on the instrument with the diag image and
`dt2probe.py capload` (see [Measuring the load](#measuring-the-load-on-your-unit)).
They show the share of each audio frame of the DSP's time that the sample
generators use. The DSP runs at 1 GHz and processes 1,500 frames a second.
The rest of each frame goes to the firmware's own work on every track
(filters, amp, effects).

| setup | native machines (CAPI off) | Capicola (CAPI on) |
|---|---|---|
| 15 STRETCH + 1 REPITCH, average frame | 11.1–12.5% (in two sessions) | 20.5% |
| 15 STRETCH + 1 REPITCH, busiest frame | not measured | about 27% |
| 13 STRETCH + 1 REPITCH + 2 SLICE in STR, average frame (OS 1.17) | not measured | 20.2–20.6% |
| the same, busiest frame (OS 1.17) | not measured | 26.4–28.5% |

- The Capicola engine costs roughly twice as much DSP time as Elektron's
  machines.
- With every track playing Capicola, it still uses only about a fifth of each
  frame.
- That leaves headroom: in testing, clicks started only once this share
  reached about 40%.
- The release image, which has no load counters, is slightly lighter than the
  diag image these numbers come from.

## Building

Everything is built on your own computer from your own copy of Elektron's OS
file. This repository contains no Elektron firmware, and the build refuses any
OS file other than the exact Elektron releases it knows, which it checks by
hash.

### The quick way

1. Download the Digitakt II OS from Elektron's support page:
   `Digitakt_II_OS1.17.syx`, or the `.zip` it comes in. OS 1.16 also works.
2. Clone this repository and run `build.sh` with that file:

   ```sh
   git clone https://github.com/hy3na-k1ng/dt2-capicola.git
   cd dt2-capicola
   ./build.sh --stock ~/Downloads/Digitakt_II_OS1.17.syx
   ```

3. The image is written to `out/dt2capicola_DT2_1.17.syx`.

The script runs on macOS and on Debian or Ubuntu Linux; see
[Compatibility](#compatibility) for what has been tested. It does four things:

1. **Installs the tools that are missing**, after asking: Homebrew on macOS,
   apt on Linux.
2. **Clones the three projects it builds with** into `deps/`, at the commits
   this repository was tested with, and builds selache. This takes a few
   minutes the first time.
3. **Keeps a copy of Elektron's OS file** in `deps/stock/`, and reads its
   version from its hash.
4. **Builds the DSP code and the OS image** into `out/`, with a full log in
   `out/build.log`.

After the first run, `./build.sh` on its own rebuilds. Options:

- **`--diag`**: also build the diag image, for
  [measuring the load](#measuring-the-load-on-your-unit).
- **`--tests`**: also set up the emulator and run the [tests](#tests). This
  takes about 6 minutes natively and longer under emulation, and needs about
  3 GB of memory per parallel run.
- **`--no-slice-ui`**: leave SLICE and GRID as stock.
- **`--os 1.16`**: choose the OS when `deps/stock/` holds both.
- **`--yes`**: install missing tools without asking.

### Building by hand

What the script sets up:

- **Python 3.12** and [uv](https://docs.astral.sh/uv/).
- **A C compiler, clang and git.** On macOS these come from the Xcode command
  line tools (`xcode-select --install`). Until those are installed, macOS still
  has `/usr/bin/git`, `/usr/bin/cc` and `/usr/bin/python3`, but they are one
  placeholder program that only opens an installer window, so a check that a
  tool merely exists is not enough.
- **GNU binutils for m68k/ColdFire**. On macOS:
  `brew install m68k-elf-binutils`; on Debian/Ubuntu:
  `apt install binutils-m68k-linux-gnu`. The **m68k GCC** (`m68k-elf-gcc`,
  `gcc-m68k-linux-gnu`) is needed only for the diag image, which carries the
  probe.
- **[selache](https://github.com/js216/selache)**, an open-source SHARC
  compiler, assembler and linker. It needs Rust: `cargo build --release`.
- **[dn2_firmware_explore](https://github.com/angellinares/dn2_firmware_explore)**,
  whose `dnfw` package reads, rebuilds and re-signs Elektron OS files.
- **[digikit](https://github.com/m-dwyer/digikit)**, only for the emulator tests.

The tools look in `deps/` first (`deps/dn2_firmware_explore`, `deps/selache`,
`deps/digikit`, `deps/stock/Digitakt_II_OS1.17.syx`). If something isn't
there, they look next to this repository:

```
workspace/
├── dt2-capicola/                      this repository
├── dn2_firmware_explore/
├── work/
│   ├── selache/
│   └── digikit/                       tests only
├── Digitakt_II_OS1.17_dist/
│   └── Digitakt_II_OS1.17.syx         from Elektron
└── dt2_builds/                        images, unless -o says otherwise
```

Anything that lives elsewhere can be pointed to with an environment variable:

| variable | what it points to |
|---|---|
| `DT2_WORKSPACE` | the workspace folder above (default: this repository's parent) |
| `DT2_STOCK_SYX` | Elektron's OS file |
| `DNFW_SRC` | dn2_firmware_explore's `src` folder |
| `SELACHE` | the selache checkout |
| `DIGIKIT` | the digikit checkout |
| `DT2_OUT` | where images go |
| `DT2_FW` | which OS to build for: `1.17` (default) or `1.16` |

Then, from this repository:

```sh
# 1. The DSP code: build/dt2gen_l1.dxe (release) and build/dt2gen_l1_diag.dxe (diag)
sh tools/build_gen.sh

# 2. The OS image
uv run --python 3.12 --no-project python firmware/build_cap.py --release --slice-ui -o dt2capicola_DT2_1.17.syx
```

`build_cap.py` checks every place it patches against the bytes it expects in
Elektron's OS before changing anything. It also re-reads the finished image,
and ends with `all checks pass`. Its options:

- **`--release`**: the image to play.
- **`--diag`**: the same plus a read-only USB probe and load counters.
- **`--slice-ui`**: the SLICE and GRID controls (the three-way CAPI and
  SLICE's BARS).
- **`-o FILE.syx`**: where to write the image.
- **For OS 1.16:** prefix the command with `DT2_FW=1.16`.

## Troubleshooting the build

If `./build.sh` stops, the message names the step. The common ones, all on macOS:

**`permission denied: ./build.sh`** — the file lost its executable bit, which
happens when the source arrives as a zip or a download rather than a `git clone`.
Run it as `bash build.sh ...`, or `chmod +x build.sh` once.

**"The Xcode command line tools are missing"** — say yes to the installer, or run
`xcode-select --install` yourself. A window opens and installs for several
minutes; wait for it to finish, then run `./build.sh` again. macOS ships
placeholder `git`, `cc` and `python3` programs that only open this installer, so
the tools can look present while nothing works.

**"Homebrew is installed but not on this shell's PATH"** — Homebrew's own
installer prints a line to add to your shell profile and leaves it to you. Open a
new Terminal window and run `./build.sh` again.

**`brew install` builds for a long time** — on an older macOS there may be no
ready-made package for the m68k compiler, so Homebrew compiles it. It finishes;
it can take half an hour.

**Anything else** — the full output is in `out/build.log`. Its last 20 lines say
what failed:

```sh
tail -20 out/build.log
```

A build that reaches `all checks pass` has verified every byte it changed against
Elektron's own OS, so an image that gets written is sound.

## Installing

1. Back up your projects and samples.
2. Send the `.syx` to the Digitakt II with **Elektron Transfer**, the same way
   as any OS update.
3. After it restarts, open a STRETCH, REPITCH, SLICE or GRID track's SRC page.
   CAPI is the parameter after PLAY.

Once more: this is unofficial software, tested on one unit. If anything
behaves strangely, go back to the stock OS.

## Going back to the stock OS

The mod changes only the operating system, never the bootloader, so Elektron's
own OS file always restores the unit:

- **If the unit starts:** send Elektron's `.syx` with Transfer, as for any OS
  update.
- **If it doesn't start:**
  1. Hold **FUNC** while powering on to open the startup menu.
  2. Press **TRIG 4** (OS UPGRADE).
  3. Send Elektron's `.syx` with Transfer's legacy OS upgrade mode, over the
     unit's **MIDI ports** (not USB).

  We have used these steps to recover a unit after a development build froze
  at startup. They come from
  [elekloader's documentation](https://github.com/irpina/elekloader#get-started).

## Measuring the load on your unit

Build and install the diag image (`--diag`), then run:

```sh
uv run --python 3.12 --no-project --with python-rtmidi python firmware/dt2probe.py hello
uv run --python 3.12 --no-project --with python-rtmidi python firmware/dt2probe.py capload --seconds 20
```

- `hello` checks the connection. `capload` reports the Capicola engine's cycles
  per frame, average and worst, as a share of the frame.
- If no port is found, `firmware/dt2probe.py ports` lists the MIDI ports, and
  `--port "<name>"` (given before the command) picks one.
- The probe only reads memory; it cannot write to the instrument.
- Flash the release image again when you are done.

## Tests

```sh
python3 test/run_tests.py host     # under a second: a C compiler and Python 3 only
python3 test/run_tests.py emu      # about 6 minutes: after ./build.sh --tests (or the workspace above)
python3 test/run_tests.py all
```

**`host`** builds the engine for your computer from the sources. It replays
recorded voices on all four machines and a set of tone tests (play modes,
tunings, stretches, retrigs). Every output must match the stored checksums in
[test/golden/](test/golden/), bit for bit.

**`emu`** has three parts:
- It builds the release and diag images for each OS whose Elektron file it
  finds (1.17, 1.16; a missing one is reported as skipped). Every patch-site
  check must pass, and both OS versions must get the same DSP image.
- In digikit's DSP emulator, with Capicola on, the output on every machine must
  match the host build bit for bit, and match the stored checksums.
- With CAPI off, every machine's output must match the unmodified firmware's,
  bit for bit.

After a deliberate change to the sound, `--update` rewrites the stored results,
and `-k NAME` runs only matching cases.

## elekloader

[elekloader](https://github.com/irpina/elekloader) builds custom OS files from
mods, and it supports the Digitakt II on OS 1.17. **It can't build this mod
yet.** By design, an elekloader mod can only change the instrument's main OS:
the ColdFire program that runs the screen, sequencer and controls. Its output
check requires every other part of the OS file to be stock. Most of this mod
runs on the instrument's DSP, whose program is a separate part of the OS file.

Two routes could make it possible:
- elekloader could add support for changing the Digitakt II's DSP program;
- the mod could carry its DSP code inside the main OS and load it at startup.

Until then, build with `firmware/build_cap.py` as above.

## Repository layout

| folder | what's in it |
|---|---|
| [capicola_c99/](capicola_c99/) | the C99 port of Capicola's core, and its checks against the original C++ |
| [capicola_c99/sharc/](capicola_c99/sharc/) | the Digitakt II generators: `dt2gen.c`, the SHARC assembly, the linker files, and `gen_host.c` (the same code built for your computer) |
| [firmware/](firmware/) | the image builders (`build_cap.py`, and `build.py` for the USB probe), the OS 1.17 address map, and `dt2probe.py` |
| [tools/](tools/) | `build_gen.sh` (the DSP build) and its helpers |
| [test/](test/) | `run_tests.py`, the emulator tracer `dt2trace_gen.py`, the stored results, and the test signals |

## Credits

- **[Capicola](https://github.com/heavylight-industries/capicola)** by
  **Heavylight Industries** is where the engine comes from: the read heads,
  the splices, and the time stretching ideas behind them. Capicola is a
  Eurorack module built on the Hermetic Modular Alchemy Lab, and the
  hardware form of the DAFx26 paper *[Keyframe Time Stretching via
  Extrema Sampling](https://github.com/heavylight-industries/dafx26-paper)*.
  - Hear what it does in the
    [audio examples](https://heavylight-industries.github.io/time-stretching-examples/).
  - Read the
    [interactive manual](https://heavylight-industries.github.io/capicola/manual.html).
  - Follow [Dialectric Studios](https://www.youtube.com/@dialectricStudios) on
    YouTube.
  - Thank you for publishing it as free software. Go and check it out.
- **[dn2_firmware_explore](https://github.com/angellinares/dn2_firmware_explore)**:
  the `dnfw` tools that read and rebuild Elektron OS files, and the USB probe
  this one started from.
- **[digihealth](https://github.com/irpina/digihealth)**: the original USB
  SysEx probe and its table of firmware addresses.
- **[selache](https://github.com/js216/selache)**: the open-source SHARC
  toolchain that builds the DSP code.
- **[digikit](https://github.com/m-dwyer/digikit)**: the DSP and ColdFire
  emulation that the tests run on, and much of the knowledge of the
  firmware's machines and parameters.
- **[elekloader](https://github.com/irpina/elekloader)**: the recovery
  procedure above, and a model of how firmware mods should be distributed.

Digitakt and Elektron are trademarks of Elektron Music Machines MAID AB. This
project is not affiliated with or endorsed by Elektron.

## License

GNU Affero General Public License v3.0 or later, the same license as Capicola.
See [LICENSE](LICENSE).

- The C99 port and everything built on it are derived from Capicola's AGPL-3.0
  code.
- The USB probe derives from digihealth (GPL-2.0-or-later), used here under
  GPL-3.0 as part of this AGPL project.
- If you distribute a modified version, including a built OS image, you must
  also offer its source.
