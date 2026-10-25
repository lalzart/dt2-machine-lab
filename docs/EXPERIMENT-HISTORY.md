# Recorded experiment milestones

These summaries retain the status and repository-wide test counts reported at
each milestone. Open items can have been resolved by later entries. For current
feature boundaries and scoped checks, use [feature guide](FEATURES.md) and
[testing guide](TESTING.md). Detailed reports and original artifacts remain at
their existing paths.

The separate [native next-bar BUF flow](BUF-NEXT-BAR-RESULTS.md)
uses **SAMPLING+YES** to record one bar from the next native first-step edge,
then automatically USE the completed take while the pattern continues.
The coupled two-take flow preserves frozen A and passes 12,858 stock-voice
blocks, two independent stock-file renders, 428 tests and SINE. This first
emulator slice requires an initialized BUF, normal 16-step pattern and all
ONESHOT tracks; configurable lengths, device feedback and hardware remain open.

The isolated [BUF performance increment](BUF-PERFORMANCE-RESULTS.md)
records/replaces takes while a native pattern plays and adds **hold SAMPLING +
push encoder C** to freeze the selected track's BUF. One four-take emulator
scenario passes native notes, two automatic releases, frozen/current playback
and 9,393 exact stock-voice blocks; 415 tests and SINE pass. This manual flow
is preserved alongside the next-bar flow above. Existing Flex R5 stays separate.

The isolated [automatic BUF cleanup](BUF-AUTO-RETIREMENT-RESULTS.md)
now selects obsolete versions and retries native retirement without host commands.
A four-record panel flow preserves current/frozen takes, refuses a retained reader
and recovers after normal playback; 406 tests and SINE pass. This remains separate
from existing Flex R5. Native BUF saving, target placement and hardware remain open.

The isolated [native BUF memory-reuse experiment](RECORDER-NATIVE-RETIREMENT-RESULTS.md)
adds the running CPU/DSP handshake for stopped-state BUF allocation release.
All 394 tests and SINE pass. Two deliberately stopped runs have matching
28-record histories and 26 native releases each; the 100-cycle qualification
is incomplete. It is separate from packaged Flex R5 below; automatic BUF
lifecycle integration and hardware behavior remain open.

The isolated [live-buffer slot-reuse continuation](RECORDER-SEAT-REUSE-RESULTS.md)
passes two exact-repeat runs of 100 native recordings with one frozen snapshot,
bounded DSP storage and CPU metadata, and exact stock-voice comparisons. It keeps
eight physical entries with unique generation tokens. All 370 tests and SINE pass;
native retirement transport, hardware placement and device operation remain open.

The [Flex RAM-bank save R5](FLEX-BANK-SAVE-RESULTS.md) adds a visible A–H bank choice after the stock name editor, previews the destination slot and preserves the track's playback settings. Exact-package native panel, project save/stock reload, immediate Discard and reset checks pass, alongside 281 tests. Old slots remain aliases for existing references; R5 hardware testing is pending.

The [Flex project-save R4 repair](FLEX-PROJECT-SAVE-FIX.md) prevents missing RAM-take references from blocking the entire project save after reboot. Missing references remain intact; live takes still require successful persistence. Native reproduction, project save/stock reload, 266 tests and reset checks pass. The user reports successful installation and Save Project As into a new project on hardware.

The [Flex save / discard R3 cleanup](FLEX-DISCARD-CLEANUP-RESULTS.md) removes the discard confirmation and UP/DN hint at the user's request. Select Discard and press YES to delete immediately. The icon, Save default and memory protections remain.

The [Flex save / discard screen R2](FLEX-DISCARD-RESULTS.md) adds visible Save and Discard actions, an original waveform icon and a take-wide discard confirmation. Discard releases the CPU audio source, preserves unrelated takes and restores recording. Exact-package UI, original project save/stock reload, 262 tests, reset/depacker and reproducible build checks pass; hardware discard remains unverified.

The opt-in [Flex save screen](FLEX-SAVE-SCREEN-RESULTS.md) follows an
unsaved recording across sample playback machines and track changes. SAMPLING
opens a visible save page; cancel/failure preserves the take, and saving unlocks
recording for that take. Packaged native UI screenshots, exact stock PCM reload,
255 source tests, reset/depacker and SINE checks pass. Build with
`--all-features --any-track --flex-save-screen`; physical operation is unverified.

The separate [stopped-sequencer arp candidate](ARP-STOPPED-PLAYBACK-RESULTS.md)
adds held keyboard playback at the current tempo/rate with PLAY off. Native
panel/recording, reset, package checks, 240 tests and SINE pass. It preserves
the R2 Capicola DSP and default build; use `--all-features --arp-stopped`.
New-candidate hardware confirmation remains pending.

**Hardware failure reported:** the initial author-release CAPI package is withdrawn. Its decoded DSP stream exceeded the stock CPU boot buffer. The [R2 repair and replacement](CAPICOLA-REDDIT-BOOT-FIX-RESULTS.md) now fit that buffer and preserve the renderer; local checks pass, physical confirmation is pending.

The [author-release CAPI R2 replacement](CAPICOLA-REDDIT-BOOT-FIX-RESULTS.md) is now the default `--all-features` backend. It directly integrates the shared Digitakt port with its release WSOLA/search/stereo assembly paths, preserves the binary switch and exact Arp/Flex/Plaits CPU image, and retains old engines through explicit build flags. Validation and the experimental OS artifact are linked in the results.

The [CAPI switch UI update](CAPICOLA-SWITCH-RESULTS.md) uses the stock AMP RSET binary switch for CAPI and packages the same source-playback DSP with Plaits, Arp and Flex. Native emulator OFF/ON checks pass; build with `--capicola-switch` to include the graphic change.

The [Capicola source-playback candidate](CAPICOLA-SOURCE-RESULTS.md) replaces the sample reader/grain handoff layer, removes independent read-head edge dips, and supports native mono/stereo with32channel banks. Full-start upstream-source/packaged SHARC, stereo loading/routing, final-output, startup and regression checks pass. Includes Plaits, Arp and Flex. Physical sound and timing remain unverified.

The separate [CAPI quality candidate](CAPICOLA-QUALITY-RESULTS.md) restores
content-adaptive stretch fades and includes all four features. Original-source
and packaged SHARC comparisons, routing, startup and regression checks pass;
physical listening and timing remain unverified. This older candidate remains available with `--capicola-quality`.

The [all-feature experimental OS](ALL-FEATURES-EXPERIMENT.md) combines
Plaits R3, CAPI time stretch, native Arp and managed Flex in one OS 1.16 `.syx`.
CPU/DSP checks and a combined Arp/Flex save/recall session pass.
It uses the DDR extension and retains the reviewed DSP image. CAPI starts OFF;
encoder C on STRETCH enables it. Hardware behavior remains unverified.

The opt-in [CPU extension experiment](CPU-EXTENSION-EXPERIMENT.md) places
Arp and managed Flex together in a 64 KiB DDR reservation with one save hook.
Native reset/ready, component lifecycles and regressions pass; hardware and a
both-active combined save/reload session remain unverified.

The [mod reuse and resource implementation](REUSE-RESULTS.md) adds shared
builders, guarded hooks/save sequencing, composition checks and optional
measured STRETCH optimizations. Existing default image bytes are preserved.

Local source, builds and repeatable offline tests for custom Digitakt II
machines. The first machine is **SINE**, a fixed 440 Hz, 250 ms oscillator
on track 1 under OS 1.16. The source runs as new SHARC instructions.

A separate [SINE controls experiment](SINE-CONTROLS.md) connects TUNE,
LEN and LEV and checks stored parameter locks through real step previews.

The [Plaits VA experiment](PLAITS-VA.md) ports one original Plaits engine
to C99, compares it with upstream C++, executes it as compiled SHARC code,
and renders through the prepared DTII voice hook. Its separate repeat commands
and remaining control/timing gaps are documented there.

The optional [Plaits resource experiment](PLAITS-OPTIMIZATION.md) compares
the reference with MAIN-only rendering and safe sharing between matching lanes.
It retains exact audio comparisons and reports emulator instruction savings.

The [resource monitor](RESOURCE-MONITOR.md) imports saved DSP and memory
records into a local diagnostic screen. The [stock OS 1.16 baseline](STOCK-RESOURCE-BASELINE.md)
compares six stock pad/settings workloads, installed-hook overhead and separate
active SINE/Plaits clips. These report emulator work and paused heap snapshots;
physical CPU/DSP utilization remains unmeasured.

The [three-model Plaits prototype](PLAITS-TRIO.md) adds two-operator FM
and analog bass drum beside VA. A dedicated MODEL control recalls engines
through real stored-lock CPU captures and prepared SHARC replay. Its repeat
commands, compiler adaptations and measured instruction costs are documented.

The [six-voice Plaits bank](PLAITS-BANK.md) adds waveshaping/wavefolding,
harmonic additive synthesis and granular formants as MODEL 3–5, preserving the
original VA/FM/BD models. It uses the same prepared emulator integration.

The [Plaits macro controls experiment](PLAITS-CONTROLS.md) gives that bank
dedicated HARM/TIMB/MORP controls, continuous macro updates and a repeatable
panel-lock capture and buffered audio audition.

The [R3 integration](PLAITS-INTEGRATION-R3-RESULTS.md) adds millisecond
duration, named models, macro LFO destinations and a track-1 selection guard.
It is a separate local build with focused CPU, panel and compiled DSP checks.

The [pattern lab](PATTERN-LAB.md) connects the firmware's normal sequencer
clock and checks a 16-step edit/PLAY/stop/edit/restart workflow for the stock
sampler and Plaits. It captures the actual performance for buffered WAV replay.

[Upload preparation](UPLOAD-PREFLIGHT.md) records the stock 1.16 upgrade
and recovery route, the checked custom container, and remaining hardware gates.

The [Flex sampling prototype](FLEX-LITE-UI-RESULTS.md) adds a remembered
destination to the original recorder: record, stop, trim, then USE a temporary
RAM sample. It supports modeled WAV input and buffered ONESHOT audition through
`python3 scripts/try-flex-lite.py` (legacy command name). This is a host-side
emulator adapter, not an on-device machine or an uploadable firmware patch.
Its recorder service and temporary sample source still depend on Python.

The [native Flex implementation](FLEX-NATIVE.md) now builds the recorder
workflow as ColdFire device instructions, with automatic sample persistence on
project save. Native UI and original project save/stock reload checks are separate
from the earlier Python prototype. A local experimental Plaits R3 + Flex package
is available. After USE, open the recorder and press **FUNC + RECORD** while
idle to name and save the selected track's Flex sample to +Drive; NO cancels.
The latest package also includes the mono-flag correction for the photographed
hardware USE error. Native naming, storage and project reload checks pass;
hardware confirmation remains pending. See the native notes for results and
current limitations.

The active [Capicola direction](CAPICOLA-STRETCH-REPLACEMENT.md) replaces
the DSP behind the existing **STRETCH** machine, retaining its selector,
controls and locks. The [R3 playback implementation](CAPICOLA-STRETCH-R3-RESULTS.md)
adds live PLAY and STRT/LEN edits with short crossfades, native completion,
and modeled master/DAC-ring checks. Sixteen distinct mono banks and thirty-two
reader lanes retain the existing 8 MiB budget and stock fallback under pressure.
Host comparisons, native playback, 138 source tests and SINE pass. Simultaneous
edits add significant emulator work; physical timing, full playhead/progress
bookkeeping, runtime ownership and hardware validation remain open.
The [combined firmware build](COMBINED-FIRMWARE-RESULTS.md) packages this
STRETCH replacement with Plaits R3 and the latest managed streaming Flex.
It is a local experimental OS 1.16 SYX, with build/container, separate emulator
startup and regression checks; it has not been sent to hardware.
An [optional CAPI comparison build](CAPICOLA-TOGGLE-RESULTS.md) adds
per-track OFF/ON on STRETCH encoder C, latched at the next native trigger.
Its second SRC page shows the received engine state. Native panel/locks, stock
and R3 audio comparisons pass; omitting the option reproduces the previous
combined firmware exactly. Physical-device validation remains separate.
The [R2 multiple-bank work](CAPICOLA-STRETCH-R2-RESULTS.md) and
[R1 replacement](CAPICOLA-STRETCH-R1-RESULTS.md) are preserved.
Separate CAPICOLA selector/RATE work is superseded.

The preserved [Capicola integration prototype](CAPICOLA-CONTROLS-RESULTS.md) has a
track-1 selector, pitch/rate/level controls and automatic mono sample preparation
in the OS1.16 emulator. Captured CPU sample transfers and triggers produce
native DSP voice output matching the host reference. Input remains capped at
12 seconds; one bank uses an 8 MiB reservation from the sample pool. Preparation
currently takes about twice the sample duration and needs a later trigger to
start playback. Automatic readiness refresh, project persistence, full memory ownership and
physical timing remain open; there is no hardware-ready Capicola package.
The optional [reserved-state build](CAPICOLA-RESIDENT-STATE-RESULTS.md) now
places working data and stacks inside that existing reservation, with native
startup, reload and compatibility checks. Instruction-code ownership in L2
and physical memory latency still need validation.
The new [selection-preparation candidate](CAPICOLA-SELECTION-PREP-RESULTS.md)
starts work when an eligible sample is selected, before the first trigger, and
exposes native progress and rejection status. The optional
[feedback build](CAPICOLA-FEEDBACK-RESULTS.md) now shows preparation ranges
and READY when SRC opens, using the existing DSP reply. Native SPI return and
buffered CPU display checks pass; automatic caption refresh remains pending.

