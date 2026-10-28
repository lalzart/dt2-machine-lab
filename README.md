# Digitakt II machine lab

The accepted experimental hardware checkpoint is **Sketch/BUF R8 for Digitakt II OS1.16**: four live
performance buffers, next-bar or immediate capture, automatic publication,
stopped recording, snapshot COPY/PASTE and a red SONG recording indicator.
The user reports this experimental build works on their device. That report
is separate from emulator tests and is not exhaustive hardware qualification.

Start with [the task, source and check map](docs/README.md), then
[current status](docs/STATUS.md). R8
[controls, architecture and limits](docs/SKETCH-BUF-CHECKPOINT.md) remain the baseline.
The accepted build recipe and binary hashes live in
[profiles/sketch-buf-r8.json](profiles/sketch-buf-r8.json). Source and documents
are committed; firmware images, captures, local dependencies and private inputs
remain ignored. No device operation runs automatically.

The new opt-in [managed Sketch profile](docs/SKETCH-MANAGED-RESULTS.md) builds on
committed R14: per-BUF recording preferences, safe admission and visible buffer
status. Buffers remain volatile; explicit Sketchbook +Drive export is available,
and project persistence is excluded. Its local validation is separate from the
accepted hardware checkpoint below.

An optional [post-recording assignment popup](docs/SKETCH-ASSIGN-POPUP.md) is
available with `--assign-popup` on the managed builder. After recording, choose
TRG 1–16 to link the live BUF to a sample track, or NO to skip. Omitting the
switch retains the previous managed build exactly.

The latest local OS combines [managed Sketch, Capicola and ARP](docs/SKETCH-CAPICOLA-ARP.md),
including the corrected CAPI switch. See [current status](docs/STATUS.md) for its
artifact and validation limits, [Capicola](docs/CAPICOLA.md) for engine identity,
and the [documentation map](docs/README.md) for current versus historical notes.

## Everyday work

```sh
./labctl doctor
./labctl unit buf-managed --list   # inspect the affected feature
./labctl unit buf-managed          # settings, popup or loading edits
./labctl unit buf                  # broader BUF behavior check
# For profile/placement changes, also use: ./labctl unit sketch-build
```

The configured Python 3.12 is selected by the launcher/build script. Unit tests
use ordinary unittest and do not launch the long coupled recorder experiments.
Native instruction cases require the explicit ColdFire bridge configuration in
[TESTING.md](docs/TESTING.md); inspect skips rather than treating them as coverage.
The checkpoint builder uses a fresh output directory and refuses MAIN/DSP bytes
that differ from accepted R8. It does not create a distributable OS or flash it.

BUF tests exclude the unrelated Arp, Capicola and old Flex suites. Use affected
suites for shared changes; keep expensive capture/audio experiments explicit.
Historical profile-build checks are explicit in `sketch-build`; `buf-full`
adds those and the earlier Unicorn BUF fixtures. The current
host's first-map SIGILL is documented in TESTING.md. No older tests are deleted.

## Current behavior

SONG opens Sketch. Encoder A remembers BUF 1–4. B/C/D/E control SRC/CHAN/LEN/MON;
F remembers BAR/NOW. FUNC+SONG records into that BUF from ordinary track pages,
regardless of the current track's sample. Stopped capture starts immediately;
BAR/NOW governs playback capture. Any trig, TRK or performance page button exits
Sketch. SONG requests red only while audio is actively being captured.

BUF aliases precede A00 OFF in the SRC selector. They use fixed reserved rows
**H124–H127**. Publication changes the live generation without assigning tracks.
FUNC+RECORD in Sketch preserves a snapshot; FUNC+STOP pastes that snapshot to the
current ONESHOT track. Selecting BUF in SRC instead keeps a live link. NORMAL
recorder DEST and ordinary sample defaults stay independent.

See [the checkpoint guide](docs/SKETCH-BUF-CHECKPOINT.md) for cancellation,
startup loading, retirement, session limits and current validation gaps.
BUF and snapshots are volatile. Current managed builds support explicit audio
export; automatic project persistence is excluded.

## Source layout

| Path | Role |
| --- | --- |
| `lab/sketch*.py`, `lab/buf*.py` | Sketch frontend, BUF adapters and fixed-slot/selector logic. |
| `lab/recorder*.py` | Shared recorder, immutable generations, loading and retirement services. |
| `lab/native/` | Lab-owned native emulator adapters and bounded probes. |
| `scripts/` | Explicit builds and integration checks. |
| `profiles/` | Reproducible feature/build recipes. |
| `tests/`, `tests/suites.json` | Scoped unit tests and ownership catalogue. |
| `machines/` | Contracts, DSP sources and preserved upstream sources/licenses. |
| `docs/`, `docs/history/` | Current guides and frozen contracts; archived experiment reports. |
| `.deps/`, `.local/`, `out/` | Ignored dependencies, configuration/private fixtures and generated runs. |

[AGENTS.md](AGENTS.md) defines the working conventions. [FEATURES.md](docs/FEATURES.md)
maps BUF, legacy Flex, Arp, Plaits and Capicola. [STATUS.md](docs/STATUS.md)
identifies the current checkpoint; [STATUS-HISTORY.md](docs/STATUS-HISTORY.md)
preserves earlier observations without making their old control maps current.

## Dependencies and local setup

The machine-lab baseline keeps DigiKit and Selache pinned by `deps.lock.json`.
The newer native BUF slice separately uses DigiKit revision
`38dfbe4ae88263511eed95691c07fc07e17b6f26`; it does not silently migrate the
baseline or change the OS1.16 addresses to OS1.17. Keep dependency trees clean.

The existing Mac setup uses ignored `.local/config.json` with `digikit`,
`selache`, `fixture` and `python` paths. The fixture inventory in
`tests/fixtures/sine-1.16.json` and `labctl doctor` verifies hashes and tool
versions. A source clone does not contain the firmware or prepared replay state.
To reconstruct from the preserved local experiment, see
[scripts/import-workspace.py](scripts/import-workspace.py) and
[the native migration note](docs/NATIVE-BUF-MIGRATION.md). Import refuses to
silently overwrite changed inputs or configuration.

## Preserved feature work

R8 is the isolated Sketch/BUF profile. Legacy all-feature builds still contain
Flex and their Arp/Plaits/Capicola adapters; this checkpoint does not change them.
The optional Sketch/CAPI/ARP package uses managed BUF and excludes legacy Flex
and Plaits. Its local validation does not replace the accepted R8 checkpoint. Historical sources and upstream licenses are
preserved; generated packages stay local.

[The R8 checkpoint record](docs/checkpoints/SKETCH-BUF-R8.json) includes exact
artifact identities, native observations, the qualified device report and open
limits. Continue from this checkpoint with focused behavior changes and retain
R8 as the comparison build.
