# Current status

2026-10-07 machine menu: optional `--plaits-before-midi` build overlay places PLAITS between Grid and MIDI, preserving machine IDs (Plaits 7, MIDI 5). The final combined package is `out/runs/flex-20sec-menu-package-02`, including twenty-second Flex and named save. Only four MAIN bytes differ from the prior package; native rank-shim/table checks, 40 source tests and container verification pass. Hardware menu behavior remains unverified.

2026-10-07 Flex duration: native USE now accepts up to **20 seconds** (960000 frames at 48 kHz), mono or stereo. Ten focused native tests and build/container checks pass. The local combined Plaits R3 + Flex package, including the explicit save dialog, is in `out/runs/flex-20sec-package-01`. Twenty-second hardware capture and timing remain unverified. See [native Flex notes](FLEX-NATIVE.md).

2026-10-07 explicit Flex save: **FUNC + RECORD in the idle recorder** opens the stock filename dialog for the selected track's accepted Flex sample. YES saves to `/recorded/<name>`; NO cancels without writing. Existing files are protected, unrelated temporary takes stay temporary, and later project saving preserves the chosen filename. Panel/dialog, guest filesystem, independent stock PCM reload, mono/stereo named project roundtrip, mono USE regression and 40 source tests pass. The local combined package is in `out/runs/flex-save-package-01`; physical write timing and hardware behavior remain unverified. See [native Flex notes](FLEX-NATIVE.md).

2026-10-07 mono correction: follow-up hardware photos show **FLEX: INPUT FORMAT**, **MAIN / MONO R / 4 STEPS / 00:71** on the previously reported ONESHOT destination. The native USE entry read a byte boolean as a whole register, converting mono into invalid stereo flag 256. The corrected entry zero-extends the byte; regression tests reproduce the old failure and pass with the fix. A replacement combined Plaits R3 + Flex package is built in `out/runs/flex-mono-fix-01`, with loader/project roundtrip, container, instruction and bounded cold-boot checks passing. The corrected hardware result remains unverified. See [native Flex notes](FLEX-NATIVE.md).

2026-10-07: [Native Flex](FLEX-NATIVE.md) implements recorder USE, owned temporary samples, native track assignment, and automatic persistence before the original project writer. Prepared native UI and original project save/stock reload checks pass. An experimental combined Plaits R3 + Flex OS package has been built and container-verified locally. Physical input, hardware operation and timing are unverified; initial limits and reproducible checks are documented.

2026-10-06: [Plaits R3 integration](PLAITS-INTEGRATION-R3-RESULTS.md) implements 100–12,800 ms duration, named models, continuous HARM/TIMB/MORP LFO destinations, and a track-1 selection guard. CPU, panel-to-wire and compiled DSP checks pass. R3 hardware behavior is unverified; R2 remains separately reproducible.

2026-10-06 r2 hardware report: user confirms normal boot and working Plaits models/controls with good sound on **track 1**. Earlier clicks/silence were on unsupported track 16. Longer LEN, named models, LFO routing and an unsupported-track selection guard remain follow-up work. This is a user listening result, not exhaustive hardware/timing validation. See [observations](PLAITS-R2-HARDWARE.md).

The CPU correction and current verification are documented in [COLDFIRE-FIX.md](COLDFIRE-FIX.md).

> **2026-10-06 hardware failure:** the Plaits r1 handoff crashed after installation at CPU PC `0x40311a64`. The rank shim uses a MOVE addressing form excluded by ColdFire. Do not install/retry this candidate. User confirmed stock 1.16 recovery, normal boot and audio via Novation Launch Control 3 DIN OUT; the generic USB MIDI adapter produced no visible device reception. See [failure evidence](../out/hardware/plaits-1.16-first-trial-2026-10-06/HARDWARE-FAILURE.md). Earlier emulator checks below remain historical evidence only.

2026-10-06: the [Flex sampling prototype](FLEX-LITE-UI-RESULTS.md) connects
the original recorder panel to temporary RAM samples. Record/stop/trim/USE,
remembered destination, discard, replacement and capacity retry pass through
actual panel events. Stereo track 1 and mono track 3 produce repeatable original
SHARC voice audio. Input is a WAV service model; physical capture, persistence,
final output and real-time operation remain outside this prototype.

2026-10-05: the local machine lab is initialized with source, repeat commands
and engineering notes. An origin remote is configured; generated artifacts stay local.

2026-10-06: the [pattern lab](PATTERN-LAB.md) now verifies normal 16-step PLAY,
two stored locks, two loops, base-value restoration, stop/edit/restart and
buffered SHARC voice audio for the prepared stock sampler and Plaits FM.
Two fresh final Plaits runs produce byte-identical control captures. The
emulator needed SSI/software-interrupt delivery, deterministic panel stepping,
and a guarded FEXT fallback for the longer DSP replay. Stock audio parity and
exact-repeat audio checks pass. The optional panel window is experimental;
real-time sound, project save/reload and hardware remain unverified.

Implemented: pinned dependency checks, guarded CPU/DSP image construction,
private-fixture import, offline SINE replay, regression checks, per-block
instruction/host-time reporting, and separate run manifests/logs.

Validation passed on 2026-10-05:

- Eight source-only harness tests, plus lint and formatting checks.
- CPU and DSP builds match the original SINE image hashes exactly.
- The migrated one-second render matches the original PCM SHA-256 exactly:
  `2a38b64c83b1636b9f1a3793f6e78c71275d0a64ca2473c2e6b20bc183673eae`.
- Measured 440.000005 Hz, peak 0.125, maximum analytic error `9.45e-6`.
- Exact repeat, stock-machine isolation, controlled clone parity, disabled-hook
  negative control, retrigger, switch-away clearing and silent return all pass.
- A separate fresh-directory import and CPU/DSP build reproduce both image
  hashes. This relocation check did not repeat the audio suite.

The full replay report is retained in
[`out/runs/20261005T040725Z-test-108cd765/manifest.json`](../out/runs/20261005T040725Z-test-108cd765/manifest.json),
with its audio, raw PCM, profiles and logs. The independent path check is
recorded in [`out/relocation-check.json`](../out/relocation-check.json).
These are local, ignored artifacts; the portable expected hashes are in
[`tests/fixtures/sine-1.16.json`](../tests/fixtures/sine-1.16.json).

The successful run resolved firmware symbols through a newly generated lab
database. The first migration attempt exposed an old default database path;
that failure report remains in `out/runs/` and the adapter now uses a cache
keyed by firmware hash and DigiKit revision.

The [SINE controls experiment](SINE-CONTROLS.md) now connects pitch, duration
and level. Stored locks reach the DSP in step previews, and an unlocked step
restores the base values. PLAY startup emits the locked values; continuous
pattern traversal remains unverified.

The [Plaits VA experiment](PLAITS-VA.md) now runs a C99 translation of the
original VA2 engine on the host and as compiled SHARC instructions. Host audio
matches upstream exactly; short target comparisons pass, with a documented
long-render numeric difference. Prepared firmware replay produces the new
audio and recovers the existing pitch/length/level locks. Repeat, stock-hook
compatibility and disabled-hook checks pass. New macro panel controls and
locks are unverified. A named `P-VA` CPU candidate is built but not UI-tested;
the actual replay reuses the SINE type-7 CPU capture.

The optional [Plaits resource optimization](PLAITS-OPTIMIZATION.md) now skips
unused AUX and shares renders only for matching complete lane states. MAIN
audio remains bit-identical in the host and SHARC comparisons. MAIN-only
uses 50.82% fewer standalone emulator instructions; both changes reduce the
whole 801-frame firmware replay by 10.73%, adding a 1,036-byte cache. These
are instruction counts, not hardware load percentages. The reference remains
the default. Divergent-lane state tests, exact repeat, stock-hook compatibility,
negative controls and the SINE regression pass.

The [three-model Plaits prototype](PLAITS-TRIO.md) now selects VA, two-operator
FM and analog bass drum. All three host ports match upstream exactly in the
bounded vectors/corners; the short compiled SHARC comparisons pass. Real CPU
MODEL locks recall VA/FM/BD/VA, with a track-1/type-7 CPU shim bypassing stock
smoothing for the discrete selector. The prepared firmware replay passes exact
repeat, VA recall, stock-hook parity and disabled-hook checks. Direct adapter
checks cover latching, independent lanes, retrigger and silent return. The old
VA image remains byte-identical. Dedicated macro labels/ranges and full Plaits
voice behavior remain unfinished; this is not all 24 models. The final report
is `out/runs/trio-final-01/report.json`; the refreshed SINE regression
`out/runs/20261005T082651Z-test-a0ec5c52/manifest.json` also passes.

Buffered GUI audition is now available through `scripts/listen-plaits-trio.py`;
see [the listening instructions](PLAITS-TRIO.md#buffered-listening-in-the-emulator-window).
VA/FM/BD previews render real SHARC voice PCM and play completed WAVs on the
Mac. The native live source matches the checked replay, but renders around 2%
of real time, so uninterrupted real-time streaming remains open.

Clean fixture generation, sample-free startup, final output, real-time audio, and
physical CPU/DSP timing remain open.

The [six-voice Plaits bank](PLAITS-BANK.md) adds waveshaping/wavefolding,
harmonic additive synthesis and granular formants as MODEL 3/4/5. All six host
engines match their upstream MAIN references exactly in the bounded vectors
and corners; compiled SHARC comparisons pass. Old trio host/target PCM and its
rebuilt image remain exact. Real CPU locks recall VA/WS/ADD/GRAIN/WS/VA, and the
811-frame replay passes exact repeat, recall, stock parity and disabled-hook
checks. The capture now verifies each actual trigger selector while setting
locks, after catching a range-dependent encoder scaling mismatch. The complete
report is `out/runs/bank-final-01/report.json`, and the SINE regression in
`out/runs/20261005T095057Z-test-5569b436/manifest.json` passes. This adds engine
choices; the existing interactive-emulator and macro-interface limits remain.

The separate [Plaits macro controls experiment](PLAITS-CONTROLS.md) now adds
dedicated HARM/TIMB/MORP metadata and continuous macro reads to all six engines.
The prepared CPU capture stores two different three-macro locks, recalls
A/B/base/A/base, and captures a HARM change during a note without retriggering.
The sample-slot transport needed a type-7/track-1 correction to retain full
TIMB values. Original engine files and the previous bank image remain exact.
Current run evidence and remaining UI/reset/boot boundaries are documented in
the control experiment note.

Read [INTEGRATION](INTEGRATION.md) before changing the firmware hook and
[DEVELOPMENT](DEVELOPMENT.md) for the next steps. Elekloader is recorded in
[ECOSYSTEM](ECOSYSTEM.md) as an optional future integration.

## Flex hardware integration boundary — 2026-10-06

The requested name is **Flex**. Historical `flex_lite` filenames remain for
reproducibility; the emulator window now uses Flex. No combined Flex + Plaits
OS has been built. The existing Flex implementation is a Python emulator
adapter, not CPU firmware: `lab/flex_ui.py` substitutes recorder responses and
services acceptance between emulator worker chunks; `lab/flex_lite.py` supplies
RAM file references, handles and sample reads through host callbacks. Playback
uses the stock ONESHOT machine. These callbacks cannot be included in a SysEx
container.

A native port must supply the temporary resource lifecycle and loader hooks,
use the actual recorder service with its locking, run acceptance in a native
worker context, and establish memory/code placement alongside Plaits R3. It
also needs failure, replacement, project reload and stock-save checks without
host substitutions. Existing modeled-input and buffered-audio results do not
cover those requirements. Do not describe a Plaits-only package as containing
Flex or treat renaming the UI as a hardware integration.
