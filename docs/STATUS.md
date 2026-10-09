# Current status

2026-10-08 combined build: [Plaits R3 + managed streaming Flex + Capicola live STRETCH R3](COMBINED-FIRMWARE-RESULTS.md) is now packaged as one private experimental OS 1.16 SYX. Exact builds, protected-section/decoder/container checks, actual bootstrap depacking, native pool boundaries, separate CPU/DSP startup, 141 source tests and SINE replay pass. The CPU checkpoint retains all 102 patch writes; two fresh DSP runs preserve code/constants/selector. Capacity remains 12-second eligible mono Capicola sources in a shared 8 MiB reservation and 20-second Flex recording. Coupled startup, physical timing, permanent L2 ownership, full STRETCH progress bookkeeping and the broader Flex lifecycle remain open. Nothing was uploaded or flashed.

2026-10-08 playback R3: [Capicola live STRETCH controls](CAPICOLA-STRETCH-R3-RESULTS.md) now follow PLAY and STRT/LEN edits without retrigger, with bounded 64-sample crossfades, native active completion and modeled master/DAC-ring verification. Sixteen simultaneous tracks on thirty-two lanes, 576 host cases, forty-eight native mode/region cases, pressure/reload/parity checks, 138 source tests and SINE pass. State adds 4.5 KiB within the unchanged 8 MiB reservation. The rapid-edit stress peaks at 4.46 million emulated instructions per block; physical timing, full phase/progress bookkeeping, ownership and packaging remain open. Earlier entries below are historical milestones.

2026-10-08 playback R2: [Capicola multiple sample banks](CAPICOLA-STRETCH-R2-RESULTS.md) now supports sixteen distinct mono sources through existing STRETCH, with thirty-two independent lanes, sharing, pin-safe retention, selective LP0 reload, pressure fallback and retry. Final fresh native comparisons, 132 source tests and frozen SINE replay pass. Host capacity tests fit sixteen twelve-second tones in 2.09 MiB, while dense seeded noise admits two banks in the unchanged 8 MiB reservation. Hardware timing, final mix, live trim/mode, full runtime ownership and packaging remain open. SINE results are in the R2 results note.

2026-10-08 replacement R1: [Capicola now runs behind original STRETCH](CAPICOLA-STRETCH-R1-RESULTS.md), retaining type 2 and native controls/locks. The extended reader passes 2,160 host comparisons; native STRETCH passes 240 control cases, longer PLAY comparisons, continuous pitch/timing, reload cancellation, 16-track shared-bank playback, fallback and stock/Plaits parity. Playback search caching cuts the representative 16-track instruction count by about 40.5%; hardware timing is still unverified. Capacity remains 12 seconds and the total reservation 8 MiB. This is one eligible mono source at a time, with stock fallback for other sources; live trim/mode changes, multiple banks, final output, complete ownership and installable integration remain open. Separate CAPICOLA selector, RATE and automatic-caption work are superseded. The earlier entries below are historical milestones.

2026-10-08 feedback continuation: [Capicola preparation feedback](CAPICOLA-FEEDBACK-RESULTS.md) sends native status through an unused reply halfword and shows preparation ranges/READY when SRC opens in the CPU emulator. Captured preparation/audio,299 reply/voice compatibility comparisons, actual native SPI2 return transmission,65536 native caption cases,12 buffered UI cases,95 source tests and SINE pass. Caption refresh is currently on page open; automatic refresh, selected-sample coupled timing, project lifecycle, complete ownership and hardware remain open. Capacity and the8MiB reservation are unchanged.

2026-10-08 Flex capacity continuation: [native streaming Save As](FLEX-CAPACITY-RESULTS.md) replaces the optional managed path's whole-take scratch copy with one 32 KiB buffer. Actual allocator pressure, cleanup/retry, retained old-handle PCM, 20-second mono/stereo, UI/project reload, 32 bounded source-reuse cycles, 94 source tests, legacy parity, combined CPU boot and frozen-source SINE replay pass. The stock CPU heap is measured at 32 MiB with power-of-two allocation classes; a 20-second stereo source occupies four MiB. The 32-identity limit remains; protected stock headroom, project-epoch GC, physical timing and hardware remain open. Default legacy output and Plaits DSP bytes are unchanged.

2026-10-08 loading workflow: [Capicola selection preparation](CAPICOLA-SELECTION-PREP-RESULTS.md) now prepares eligible track-one mono samples before a trigger or voice assignment in the optional `capicola-selection` build. Native progress/readiness, cancellation, invalid-input rejection, same-address reload and first-trigger voice output pass. The 12-second limit and 8 MiB reservation are unchanged. Prior image bytes, 184 stock/Plaits comparisons, two fresh DSP startup runs, 63 unit tests and SINE replay pass. Screen feedback and its return transport, complete runtime ownership, project lifecycle and physical timing remain open.

2026-10-08 working-memory continuation: [Capicola reserved state](CAPICOLA-RESIDENT-STATE-RESULTS.md) moves constants, working state, private stacks and tables into the existing 8 MiB reservation in an optional build. L2 payload drops to 64,588 code bytes. Exact builds, 184 stock/Plaits comparisons, captured sample loading/reloading, two identical fresh DSP startup runs, 63 unit tests and SINE replay pass. Twelve-second capacity is unchanged. The observed RTOS heap is in L1; permanent L2 code ownership and physical DDR timing remain unresolved.

2026-10-08 panel-to-voice integration: [Capicola controls and automatic loading](CAPICOLA-CONTROLS-RESULTS.md) pass native CPU checks, emulator panel selection/RATE editing, captured stock LP0 sample loading, automatic bank preparation and complete triggered voice comparison (maximum error 1.49e-8). The selector allocation is corrected to 36 bytes. Twelve-second capacity and the 8 MiB pool reservation remain. Sixty unit tests and SINE regression pass. This is a track-1 mono emulator prototype; preparation is approximately twice the sample duration and playback requires a later trigger. Readiness UI, persistence, full runtime arena ownership, final-mix validation and physical timing remain open. Entries below are historical milestones.

2026-10-08 memory integration: [Capicola sample-pool reservation](CAPICOLA-OWNED-MEMORY-RESULTS.md) carves eight MiB from the existing pool, leaving 392 MiB. Native allocation-boundary checks and preparation/voice-hook comparisons in the reserved region pass. Preview memory and the legacy Capicola build are preserved. Fresh allocator state is required; stock scheduling and CPU selection remain open.

2026-10-08 native preparation: [Capicola PCM worker](CAPICOLA-NATIVE-PREP-RESULTS.md) builds banks in bounded count/write passes, with cancellation and generation guards. Host twelve-second and short native SHARC comparisons pass. Exact integer ratio rounding fixes the tested int16 analyzer timestamp discrepancy. Stock scheduling, memory ownership and CPU menu remain open.

2026-10-07 integration: [Capicola R1 voice hook](CAPICOLA-INTEGRATION-R1-RESULTS.md) runs compiled stretch alongside Plaits with guarded prepared banks. Actual voice-entry, Plaits parity, stock fallback and invalid-bank checks pass. Existing Plaits/Flex MAIN is unchanged. Native loading and CPU selection remain open; no installable Capicola OS yet.

2026-10-07 final capacity choice: [Capicola is capped at twelve seconds](CAPICOLA-TWELVE-SECONDS-RESULTS.md): 576,000 mono input frames, at most 24 seconds of output, and 6.59 MiB worst-case shared bank storage. Thirty host and five SHARC comparisons, 59 tests and the SINE replay pass. The ten-second results below are historical.

2026-10-07 capacity: [Capicola ten-second banks](CAPICOLA-TEN-SECONDS-RESULTS.md) support 480,000 mono input frames and up to 960,000 output frames. Count-before-load storage accepts dense input; each bank is shared by 76-byte target readers. Thirty host long-signal comparisons and five standalone SHARC full-source/large-bank endpoint checks pass. All 59 source/native CPU tests and the SINE replay regression pass. The structural bank maximum is 5.49 MiB per distinct sample, allocated according to measured keyframe count. Firmware memory ownership, target analysis parity and physical timing remain open.

2026-10-07 continuation: [Capicola split timestamps](CAPICOLA-SPLIT-TIME-RESULTS.md) remove the direct-port precision blocker. The host passes 125 audio comparisons and 3,000 duration cases; standalone compiled SHARC reader comparisons pass six cases with exact repeat. The full source/native CPU suite passes 54 tests, and the SINE replay regression passes. Target analysis still differs slightly on one two-tone fixture, so the target experiment remains partial. No firmware integration, listening or physical timing is claimed.

2026-10-07: [Capicola finite-sample prototype](CAPICOLA-PROTOTYPE-RESULTS.md) has exact host C99/reference PCM across 90 matrix cases and three decimal-rate cases. Forty-six source/native CPU tests pass. One extreme-setting pitch metric remains incomplete. A compiled SHARC numeric probe confirms that the pinned compiler narrows double to four bytes despite its 64-bit option; the full target audio port is deferred pending a precision-preserving position representation. No firmware integration or quality improvement is claimed.

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


### Optional Flex source ownership — 2026-10-08

The opt-in bounded native source-retirement stage now passes strict backing-reference
negative controls, 20-second mono/stereo, failure cleanup, UI/project reload,
32-cycle reuse, combined boot and stable-source SINE replay. Default legacy images
remain byte-identical. More than 32 published identities, independent safe byte
admission and unsaved/project-epoch reclamation remain unimplemented.
[Results, exact artifacts and remaining invariants](FLEX-MEMORY-IMPLEMENTATION-RESULTS.md).
