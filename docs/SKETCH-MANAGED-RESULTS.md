# Managed Sketch buffers — OS1.16

Local successor to committed Sketch R14 (`34284b5`). Implemented and locally validated, without project persistence.
Use the opt-in `profiles/sketch-managed.json`; ordinary build flags retain the
exact committed R14 output. This does not replace the accepted hardware checkpoint.

## What changes on the instrument

SONG still opens the compact Sketch page. A chooses BUF 1–4. Each BUF now keeps
its own B source, C channel, D length, E monitor and F start preference. Switching
BUFs switches those displayed settings. Editing Sketch does not edit the normal
sampler's preferences. A capture borrows the chosen settings while the recorder
owns the operation, then restores the normal sampler after publication or refusal.

FUNC+SONG retains the current capture/finish gesture from ordinary track pages.
While playing, BAR waits for the bar and NOW starts immediately; stopped capture
starts immediately and the same gesture finishes it. LEN supports 16/32/64 steps
within the existing ten-second capture ceiling. The existing filtered encoder
response is retained.

The bottom right shows EMPTY, READY, WAIT, REC, BUSY, FULL or ERROR for the
selected BUF. FULL means no currently vacant generation seat; occupied or
uncertain storage is not reclaimed just to admit a recording. Existing background
retirement can make a seat available once it proves the old allocation unreferenced.
A refused admission does not change the normal sampler settings or accepted audio.

Any compatible track can select the existing BUF aliases in SRC. Replacement
preserves those assignments. FREEZE retains an immutable generation in RAM;
subsequent recordings can replace the live BUF without changing that frozen take.
The existing Sketchbook opens with SONG then DOWN for preview and explicit +Drive
export. Original Samples and normal recorder workflows remain available.

**No project persistence.** Buffers, frozen takes and their preferences are
volatile. Power-off may discard them. FREEZE alone is not a disk save. Only an
explicit Sketchbook export keeps a sample on the +Drive. Existing project-switch
ownership guards remain; no project format, automatic restore or background save
is introduced.

## Engineering boundary

This adds a small native ColdFire settings/admission/status service around the
existing recorder, publication, immutable-generation, reader protection and
retirement machinery. It does not replace the DSP sampler or invent a second
allocator. Four live BUF identities, eight generation seats, eight FREEZE
identities, one recorder and the existing ten-second bound remain. Restrictive
reader fences may still refuse reclamation; ONESHOT remains the qualified reader
path. A broad Octatrack engine, simultaneous recorders, arbitrary-length streaming,
new time stretching and unlimited audio RAM are not implemented by this profile.

The added CPU reservation is 20 KiB including guards/alignment, with 16 KiB for
code/data. The inherited 360,448-byte reservation and every inherited arena's
location are preserved. DSP and the stock sample-file format are unchanged.

Source entry points: `lab/sketch_managed.py`, optional bindings in
`lab/sketch.py`, `lab/sketch_panel.py` and `lab/sketch_device.py`.
The proposal and reuse boundary are in [SKETCH-MANAGED-BUFFERS.md](SKETCH-MANAGED-BUFFERS.md).

## Validation

- Scoped `buf core integration`: 239 tests passed, no skips, with the explicit Rust
  ColdFire bridge. Ten new managed-buffer tests cover independent preferences,
  real encoder scaling, supported lengths, latched destination, normal-setting
  restoration, full/busy refusal, stale project/wrapper refusal, asynchronous
  failure, manual finish, status and deterministic placement.
- `out/runs/sketch-managed-build-20261026-01`: deterministic local MAIN/DSP build.
  `DeviceBuild` successfully reloads the sealed manifest with zero source changes.
  MAIN is `4c7f99100063de90164bf47197761a2fb0d19e45a4763219e5a40b44ebcb58bf`.
  DSP is unchanged: `37270ca2f528a6dae7d0bd8aa8f463d21e523c1e82217fa12717d849f1f568ae`.
- The non-managed R14 build remains exactly
  `0f85c967ff1034e3e22ac0d9134fd33e89d198e0df9693076a6d924493adfd1d`.
- SINE replay passed independently in
  `out/runs/20261026T140429Z-test-2fe3f626`. This preceded the final CPU-only
  ownership guard and reservation refinement; DSP and SINE sources are unchanged.
- Coupled development runs `sketch-managed-native-20261026-01` and `-02` passed.
  They are retained as superseded development evidence. Run 02 also proves that
  the compact panel completes full native bitmaps: the general emulator panel
  latch can capture an intermediate comparison buffer with only changed pixels.
  The new observer stops after the target draw returns and copies that bitmap
  without constructing pixels. No production drawing workaround was required.

- Final `out/runs/sketch-managed-native-20261026-03/report.json`: passed in
  380.7 seconds on the exact final MAIN/DSP. Nonzero capture, per-BUF LEN/START
  isolation, normal-settings restoration, complete native UI bitmaps, FREEZE A,
  replacement B, unchanged assignments/frozen A, original Samples, naming cancel,
  preview cancellation/nonzero modeled output, two saves, duplicate refusal,
  disabled-readback failure and successful retry passed. CPU code and every arena
  canary remained exact. The run's source fingerprint remained stable.
- Its local `candidate-test-fixture.syx` has SHA-256
  `a19f0c36c71174ea285a957bfa6aaf58a1c19d96e9abf19d386096e2308bb52d`.
  This is the emulator test container, not a hardware-qualified release.
- `out/runs/sketch-managed-reload-20261026-01/reload.json`: independent stock
  CPU cold boot and original sample loader passed. Both exported native files
  were byte-exact (147,152 and 110,928 bytes); both PCM channels of each sample
  reloaded exactly. This observes stock loader output with modeled card/DSPI2,
  not physical +Drive hardware or a DSP listening test.
- [Final validation index](../out/runs/sketch-managed-build-20261026-01/validation.json)
  records report/container hashes, matching build/native source fingerprints,
  final MAIN/DSP identities and the raw 239-test log. Scoped Ruff and
  `git diff --check` pass.

Native ColdFire instructions, coupled CPU/SHARC with modeled card/recorder,
PCM readback, real-time listening and physical hardware are separate evidence layers. No physical timing, audible click-free replacement, broader
machine-reader compatibility, or device validation is claimed. Nothing has been
flashed, committed, pushed or published.

Native recording bitmap from the final run:

![Sketch recording with per-buffer settings](../out/runs/sketch-managed-native-20261026-03/manual-recording.draw.png)

## Reproduce

From this checkout, with its private OS1.16 fixture and pinned local dependencies:

```sh
./labctl doctor
python3 -B scripts/build-sketch-managed.py out/runs/managed-build-NEW
DT2_BUF_SELECTOR_CORE='/Users/lanceship/Documents/Codex/Digitect firmware research project/work/buf-selector-implementation-20261023-01/lab/out/runs/selector-panel-11/libcfselector.dylib' \
  ./labctl unit buf core integration

python3 -B scripts/check-sketch-managed.py out/runs/managed-native-NEW \
  --reference-spec out/runs/sketchbook-r14-native-20261026-01/spec.json \
  --dsp-build out/runs/managed-build-NEW/sketchbook-dsp \
  --reset-inputs out/runs/sketchbook-persistence-20261025-01/dsp-inputs-05 \
  --native-upstream '/Users/lanceship/Documents/Codex/Digitect firmware research project/work/digikit-main' \
  --native-boot '/Users/lanceship/Documents/Codex/Digitect firmware research project/work/buf-stopped-recording-20261024-01/lab/out/runs/stopped-native-02/native-boot'

python3 -B scripts/check-sketchbook-reload.py \
  out/runs/managed-native-NEW out/runs/managed-reload-NEW \
  --native-upstream '/Users/lanceship/Documents/Codex/Digitect firmware research project/work/digikit-main' \
  --native-boot '/Users/lanceship/Documents/Codex/Digitect firmware research project/work/buf-stopped-recording-20261024-01/lab/out/runs/stopped-native-02/native-boot'
```

Every command needs a fresh output directory. The reset input is accepted only
if its authenticated DSP hash equals the newly built unchanged DSP. Native checks
use DigiKit `38dfbe4` with the existing lab-owned recorder/boot adapter and modeled
nonzero external input. The default lab dependency remains `277760a`; neither
checkout was edited. The reload check cold-boots original stock firmware and
loads the explicitly exported sample files. It does not restore a project or
persist volatile BUF identities/preferences.

## Startup visibility and early reservation — 2026-10-27

The managed builder now accepts `--buf-loading` and `--early-buf-setup`.
The latter requires the former; both remain optional so previous managed and
assignment-popup images can still be reproduced exactly.

With loading visibility, BUF 1–4 remain present before A00 while their backing
slots are unowned. They display `LOADING`; highlighting them scrolls the label
into view without changing the assigned sample. YES stays in the list until the
slot is ready, then assigns it normally. Ordinary A–H samples and NO restoration retain their mappings. Once setup succeeds, the
same list resolves the real BUF slots and displays EMPTY or READY. Sketch's
buffer-status field also displays LOADING, including a completed take waiting
for project loading. A diagnosed setup conflict displays UNAVAIL. Active
recording feedback remains REC. The GUI retries through the existing batch and
busy guards even when the normal recorder stays at DEST=NORMAL.

Early setup is a metadata reservation, not loading or restoring BUF audio.
Authenticated OS1.16 code calls the initial pool clear at `0x4004e976`, then
reaches the existing batch hook at `0x4004e97c`, before constructing its load
list and calling the per-sample loader at `0x4004eaac`. At this boundary, the
new optional helper checks that the batch wrapper is the active project's
wrapper, that no capture is active, and that the batch is not poisoned. It then
uses the original guarded initializer: four fixed public slots plus eight
vacant private generation slots, validating the complete plan before ownership.
Busy state, occupied H124–H127, or insufficient free slots retain the fallback
after batch completion. No ordinary sample reference is overwritten.

Publication of a new recording still waits for the completed load batch. The
stock sample order, PCM allocator, DSP, guards and RAM reservation are unchanged.
This does not remove the earlier project-read/clear stage or add persistence.

Source: `lab/buf_loading.py`, optional selector/poll/status variants, and the
existing batch-entry hook. Build with:

```sh
python3 -B scripts/build-sketch-managed.py out/runs/NEW-STARTUP-BUILD \
  --assign-popup --buf-loading --early-buf-setup
```

Leaving both new switches off reproduces the assignment-popup MAIN
`b62584d425f31c22f1e8013234e23f03c36177d8ab6a0312767e7568d91d4431`.
The startup candidate MAIN is
`2a4dea25f0818ae8f8eb5445dadbc722dbc4075ccdc68d48dce1b80a35f630d8`;
its unchanged DSP is
`37270ca2f528a6dae7d0bd8aa8f463d21e523c1e82217fa12717d849f1f568ae`.
Physical startup timing and controls require a device trial.

Validation of this startup candidate:

- `out/runs/buf-loading-build-20261027-05/validation.json` records exact hashes,
  inputs, and the source-matched native results. Build output is in that same
  directory; the optional switches off still reproduce the earlier image.
- 265 BUF/core/integration tests passed with the Rust ColdFire bridge, with no
  skips. Checks cover all ordinary slot mappings, pending selection/YES,
  ready confirmation, status labels, busy/capture/context guards, occupied
  public slots, and post-batch recovery. Ruff and `git diff --check` passed.
- `out/runs/buf-loading-native-20261027-03` passed the complete cold-boot,
  capture, FREEZE, assignment-popup, preview and explicit export workflow,
  including failure/retry controls and intact code/arena canaries. All four
  public identities were prepared in 11,509 target CPU instructions before
  the first project sample load. The 297 ordinary load calls retain the exact
  arguments and order seen in the previous assignment-popup candidate.
- `out/runs/buf-loading-panel-20261027-03` contains inspected native bitmaps
  showing Sketch LOADING, highlighted `BUF 1 LOADING`, then EMPTY in the same
  open list. The early-setup switch was deliberately disabled to exercise the
  real pending batch; the host did not inject setup/readiness state.
  `out/runs/buf-loading-panel-20261027-04` also proves that YES while pending
  retains the current sample, and YES after setup assigns the highlighted BUF
  without another cursor movement. Both use the same final selector source.
- The initial native run `...-01` is retained as a source-drift failure after
  the automatic retry change; `...-02` passed a superseded selector candidate.
  Neither is used as the delivered package's validation.

The local package is
`out/runs/buf-loading-os-package-20261027-01/EXPERIMENTAL_SKETCH_EARLY_BUFFERS_OS1.16.syx`
(SHA-256 `5d5376f6646d5371368ceb80f0a09ae0a5d2a8687ffff0918bea272b2aaec640`).
Its MAIN, DSP and complete SysEx match the final native-tested fixture exactly.
Reproduce it with the ignored `package-os.py` in the build directory and a fresh
output directory. The package manifest records the source/dependency identities
and framing, checksum, decoding, protected-section and staging checks.
No firmware upload, hardware test, commit or publication was performed.
