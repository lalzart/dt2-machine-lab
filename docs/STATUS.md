# Current status

2026-10-23 device follow-up: the user reports the clock-correction firmware now
works. A source/native-panel investigation confirms empty BUF selection through
the stock encoder-D quick list (C44/slot 300 in the prepared project), A00's
lower clamp and unchanged A/B OFF navigation. Four BUF aliases before A00 are
the next requested UI; they are not implemented here. Existing slots share the
stock allocator, so special slot numbers alone do not remove startup exclusion.
Deferred ARM and recorder capture before publication are separate candidates
requiring pending-load interleaving and source-lifetime proof. Doctor, authenticated
static survey, selector-byte parity and the bounded native navigation checks
pass; no new captures, firmware or dependency changes. Earlier device-unconfirmed
entries below describe their evidence at the time.
[Findings, screenshots and next implementation](BUF-SELECTOR-AND-STARTUP.md).

2026-10-23 Sketch clock candidate: user confirms advancing BUSY LOAD clears
after waiting, then running playback reaches REF CLOCK 0. The opt-in clock
profile now uses the stock OR transport predicate and semantic normal16/mode0/
scale2 checks in both IRQ and CHECK. Passive WAIT SAMPLES preserves the shared
loader guard. 251 scoped units, specific clock labels, full-container startup,
upload/backpressure, stream/package integrity and three proof-refusal controls
pass. A focused native run observes two real bar receipts, rejects a test scale
change, cancels before start, then captures/publishes 112,928 modeled stereo
frames with assignments/NORMAL DEST and post-capture code/canaries intact.
Its first capture also published, but a final harness address-reading bug left
that report failed; the corrected fresh run passes. Two total model captures.
Firmware bytes stayed exact across that fix; same-firmware SINE is reused.
Original/ARM/sample profiles, DSP, pins and upstream stay exact. No hardware
transfer; exact device clock cause, physical recording and timing remain open.
[Candidate, use notes, screenshots and evidence](SKETCH-CLOCK-CORRECTION.md).

2026-10-23 startup sample-operation diagnostic: user identifies `BUSY FREEZE 1`
as the first refusal after power-on and PLAY, before later `REF CLOCK 0`.
Read-only cold startup of the exact first diagnostic container observes 1,915
balanced stock load/unload/clear operations, peak nesting three, zero at UI
readiness and after PLAY; the device failure is not reproduced. A separate
opt-in diagnostic now latches the outer operation and slot with the busy count,
using a generic SAMPLE fallback for unknown/returned outer context. 249 scoped
units, native cold-start counter/observer agreement, seven injected UI controls,
upload/backpressure, package integrity, two missing-proof refusals, Ruff and SINE
pass. Zero new recordings; no guard clearing or automatic retry. Default and
first diagnostic MAIN/DSP/packages stay exact. Pending clock work is held and
excluded. No hardware transfer; physical cause and timing remain unconfirmed.
[Diagnostic, screenshots and evidence](SKETCH-STARTUP-SAMPLE-DIAGNOSTIC.md).

2026-10-23 Sketch ARM diagnostic package: user reports the original experimental
firmware reaches the device UI but ARM returns BUSY/REFUSED with REC READY and
BUF IDLE after a power cycle. Root cause is unconfirmed. An opt-in profile now
reports the first failed admission predicate and its observed value, preserving
every guard, result ABI and admitted transaction. The ordinary MAIN and all DSP
bytes remain exact. 212 BUF/core plus 30 integration tests pass; native complete
container application startup, two injected guard/UI cases, upload/backpressure,
package integrity, two packager refusal controls, Ruff and SINE pass. Zero new
recordings. Original package, feature profiles, pins and upstream are preserved;
the assistant has not transferred the diagnostic image. [Package, labels and evidence](SKETCH-ARM-DIAGNOSTIC.md).

2026-10-23 local Sketch-only OS1.16 experimental package: fresh MAIN/DSP and
the complete SYX match the successful native recorder workflow byte-for-byte.
Package/seal/checksums, protected sections, MAIN depack and DSP staging bounds,
independent boot-stream checks and native CPU upload/backpressure pass on the
final source inventory. Full-container CPU application startup with independently
initialized DSP application startup renders Sketch: code/canaries intact,
1,620 LP0 units, 6,878 DSP frames and zero missing blocks. The packager refuses
mismatched-container and stale-source evidence. 238 scoped units and focused
Ruff/format checks pass; saved same-firmware recorder/audio/SINE proofs are reused
with zero new recordings. Firmware emitters, dependencies and upstream stay
unchanged. No hardware transfer or trial. Physical ROM/SPI, placement, recorder,
normalization and timing remain unverified. User direction: BUF/Sketch replaces
the previous Flex implementation in a future combined OS; old profiles remain
preserved as reference. [Package, evidence and reproduction](SKETCH-EXPERIMENTAL-PACKAGE.md).

2026-10-23 native BUF recorder connection: opt-in DigiKit `38dfbe4` now runs the
original ARM/STOP/worker/loader/FREEZE jobs against the existing nonzero recorder
service model. One two-take flow passes over 53,232 native DSP frames: two
112,960-frame stereo captures, four retained old-reader lanes across B, frozen A
and shared selectors intact, and cancellation of an active third candidate.
Stock CPU file-load PCM is exact; 96 saved blocks repeated twice match stock
voice PCM, whole replies, master mix and DAC-ring data, with a differing wrong
source control. 208 BUF/core units and same-flow-source SINE pass. The callback
comparison needed its authenticated prepared fixture rather than the live cold
state; that comparator-only correction passes in a separate zero-recording run.
Firmware emitters, BUF/FREEZE/Flex backend, upstream source and pins stay exact.
Native input/normalization remain modeled; mono, other native capture lengths,
physical timing and hardware are unqualified. [Results and reproduction](NATIVE-BUF-RECORDING.md).

2026-10-23 BUF multi-bar recording: native next-bar ARM now latches LEN 16/32/64
as one/two/four normal bars. Consecutive native receipts drive STOP; missed/late
receipts and setting changes cancel. The existing ten-second sample limit is
enforced during capture, with TOO LONG feedback and the previous take preserved.
156 scoped BUF tests, Ruff and same-source SINE pass. One bounded coupled run
passes 26 checks over 57,888 DSP blocks: two-bar A, FREEZE A, four-bar B, then
cancellation of a third candidate after one bar. Four old-reader pointers,
frozen A, accepted B and all assignments remain intact; zero CPU faults.
Saved-page stock-file voice PCM matches over 96 blocks repeated twice, with a
wrong-source control and zero extra recordings. Modeled completion/publication
delays are 384 ms (two bars) and 772 ms (four bars); timing optimization remains
separate from this extension. Clock, queue/load/publication and cancellation
emitters, FREEZE backend, Flex, DSP and dependencies are unchanged.
No device package or hardware trial. [Results and screenshots](BUF-MULTIBAR.md).

2026-10-23 Sketch ARM feedback: the opt-in real ARM profile now follows its
admitted BUF through waiting, recording, processing/loading and cancellation,
then reports READY, CANCELLED, FAILED or STALE. Native transaction count and
context guards reject stale success; selection/navigation cannot relabel the
target, and newer actions keep their own messages. 151 scoped BUF units pass.
One native modeled-input capture plus two pre-start cancellations passes 21
panel checks, with exact assignments/accepted take, zero faults and correct
feedback when reopened. The dry profile passes 20 checks without jobs, and
same-source SINE compatibility replay passes.
Backend/FREEZE/memory policy, normal Flex and dependency pins are unchanged.
This UI source follow-up is not part of the earlier sealed device image;
physical behavior and the separate native-emulator migration gate remain open.
[Behavior and evidence](SKETCH-ARM.md#live-feedback).

2026-10-23 first opt-in native migration slice: a copied current-upstream boot
crate adds an authenticated-reference constructor. It fixes the zero-match
startup-anchor case caused by Sketch hooking `0x40033d00`; the earlier
duplicate-signature explanation was incorrect. The complete candidate container
now reaches application-ready with native DSP coupling and renders Sketch,
without a host MAIN overlay. Reset segments/BSS, code and canaries pass;
1,620 LP0 units drain with no missing SPORT blocks. A small native saved-page
BUF adapter matches old-runtime voice PCM for all 96 A/retained-A/B/frozen-A
blocks, repeats exactly, preserves reader/frozen roots and detects a wrong source.
New-runtime stock and candidate replies match, but old/new replies differ.
The default migration gate stays closed. 229 scoped units, Ruff and same-source
SINE pass; no new recording or firmware change is made. The lab pin and upstream
checkout remain untouched. [Results, screenshot and remaining reply gate](NATIVE-BUF-MIGRATION.md).

2026-10-23 Sketch boot-stream/upload correction: the device recipe now puts all
added blocks before stock FINAL, pads the gate payload to four-byte alignment,
and updates FIRST's next-application span/checksum. The stock init application,
all existing loaded bytes and CPU MAIN remain exact; the ordinary emulator
DSP/metadata are unchanged. Independent Python/Rust stream rules pass, and the
old `-09` stream is rejected. Native CPU reset, section lookup, allocation,
MAIN depack and sender transmit 339,073 exact bytes including command 3, then
one terminal frame. Two bounded busy holds prevent pointer advance/writes and
resume without byte loss. Fifteen saved-page DSP controls and 229 scoped unit
tests pass, with zero recordings. Full candidate container integrity passes;
direct native construction cannot match the intentionally hooked main-loop
entry. The sender check therefore installs candidate MAIN before CPU
instruction zero over a stock-MAIN/candidate-DSP input container. Actual ROM,
SPI FIFO/tail acceptance, physical memory and hardware remain unverified.
The older `-07`/`-09` builds retain only their recorded emulator/application
scope. Current sealed build is `-13`, with final upload evidence at
`sketch-rom-upload-20261023-07`. SINE compatibility and focused Ruff also pass;
all firmware/runtime sources remain exact after SINE, with only final
standalone upload validators subsequently adjusted for the constructor limit.
[Correction, exact inputs and limitations](SKETCH-BOOT-UPLOAD.md).

2026-10-23 Sketch coupled application startup: stock and corrected `-09` BUF
both reach ready from CPU reset and DSP loader application entry, with the
native peer attached before the CPU's first instruction. Native control/SPORT
and all 1,620 card sample-transfer units run without a prepared ready snapshot.
BUF opens/renders Sketch through panel input; all 45 reset segments, BSS/source
clearing, 30 CPU canaries, CPU code/hooks and added DSP code pass. The measured
disconnected-DSP negative refuses; positive results repeat exactly apart from
wall time. 145 BUF units, Ruff and final-source SINE pass with zero recordings.
Only validation files are added; firmware, images, pins and card/SYX remain exact.
DSP ROM/boot upload, whole-container startup and physical memory/cache/DMA/stack
behavior remain outside this result. [Scope, results and screenshot](SKETCH-COLD-STARTUP.md).

2026-10-23 Sketch DSP boot-memory correction: the earlier prepared-emulator
layout zero-filled all 8 KiB of ADI's reserved boot workspace. Device build `-09`
moves the 16 KiB retirement-gate state to lower L2, including its wrapper
scratch/stacks and seal consumer, and refuses any boot-workspace write.
MAIN and the ordinary emulator DSP/metadata remain byte-exact. Stock and
candidate execute 250 million DSP startup instructions to the same state;
all six added arenas remain exact. Fifteen native seal/refusal controls and
227 BUF/core/integration checks pass with zero new recordings.
Twenty-four saved-page native blocks have exact voice PCM/reply parity; actual
DSP depacking/staging, focused Ruff and final-source SINE also pass.
The old `-07` image remains emulator evidence, unsuitable for hardware packaging.
Paired CPU/SHARC cold boot and physical memory/cache/DMA/stack ownership remain
open. [Correction, evidence and next gates](SKETCH-DSP-BOOT-MEMORY.md).

2026-10-23 Sketch at device addresses: the exact sealed MAIN/DSP now pass the
prepared coupled workflow at the new DDR addresses. Two captures, one native
held-SONG FREEZE, 23 checks and 34,249 native DSP blocks preserve shared/current
B, frozen A and four old-reader pointers. All code and 30 canaries remain exact;
there are zero old-arena accesses and zero CPU fault pages. PCM takes, LP0 histories,
wire and live voice hash match the earlier layout exactly. 144 BUF tests, Ruff
and final-source SINE pass. Fresh stock-file voice PCM matches exactly over
96 blocks repeated twice, with a differing wrong-source control and no extra
recordings. Firmware/DSP/build sources remain unchanged.
Paired cold startup, physical memory/cache/DMA/stack behavior, timing and hardware
remain open; obsolete-generation retirement at the new addresses was not exercised.
[Workflow, evidence and remaining gates](SKETCH-RELOCATED-VALIDATION.md).

2026-10-23 Sketch device placement: separate stock-only build relocates the
current native Sketch/BUF install graph into a guarded 352 KiB experimental DDR
range. MAIN fits the existing staging ceiling; the accepted BUF DSP is unchanged.
Native CPU reset copies/initializes every segment, reaches ready and renders
Sketch through panel input. Modal ownership, BUF selection/reopen, code and all
canaries pass; disabling the loader fails as expected. The source graph matches
all 282 prepared-installer payloads and 28 hooks with zero recordings; 224 scoped
BUF/core/integration tests, actual compressed-stream depackers and final-source
SINE pass. The original default Arp/Flex CPU build remains byte-exact.
This is local CPU placement/startup evidence,
with modeled peripherals. Paired coupled cold startup, relocated recording,
physical cache/DMA/stack ownership, composition and hardware remain open.
No SYX or device transfer. [Layout, evidence and remaining gates](SKETCH-DEVICE-PLACEMENT.md).

2026-10-23 Sketch combined DSP validation: two native captures and one held-SONG
FREEZE pass through 34,249 native SPI/SEC DSP blocks. T1/T5 share BUF 1, T6 selects
frozen A, and B replaces the shared BUF with a fresh identity. Four active old
voice lanes retain their pointers across publication; later triggers sound B
on the shared tracks and A on T6. Fresh stock-file comparisons match voice PCM
exactly over a 96-block scenario repeated twice; a wrong frozen-B reference
differs. 138 BUF units, final-source SINE and source preservation pass. All
firmware emitters/DSP sources stay unchanged. Publication takes 196–197.333 ms
after capture in the model, after the following bar's first trigger. Input,
cadence, LP0 delivery and SEC reset remain modeled; final mix, physical timing,
listening, target placement/startup/packaging and hardware remain open.
[Results and reproducible checks](SKETCH-VALIDATION.md).

2026-10-23 Sketch real FREEZE: an additional opt-in profile connects held SONG
to generation-specific global-BUF admission and the existing native FREEZE
worker. Two native captures publish A then B into BUF 2 with DEST=NORMAL;
frozen A remains exact across replacement, and every track assignment survives.
One 1.6-second modeled hold submits one job; empty/recording BUSY controls submit
none. 138 scoped BUF tests, 13 native checks, default dry panel, stock Song
opt-out and real ARM/FREEZE filename-modal ownership pass. Sources and default
FREEZE queue payload stay exact outside the intended edits; final-source SINE
replay passes. Recorder input/LP0
are modeled; coupled DSP workflow, device placement/packaging and hardware remain
open. [Controls, ownership, results and screenshots](SKETCH-FREEZE.md).

2026-10-23 Sketch real ARM: an additional opt-in profile connects FUNC+SONG in
either key order to shared arm-only BUF admission. One native empty-BUF-2 capture
starts at the next first-step receipt and automatically publishes 112,928 stereo
frames while recorder DEST stays NORMAL and all assignments remain exact.
Repeated ARM refuses without canceling. Recorder DEST=BUF 3 then coexists with
Sketch BUF 2; NO cancels that request before capture and preserves the take.
130 scoped BUF tests, 16 native checks, default dry panel, stock Song opt-out,
real-profile filename-modal ownership and stable-source SINE replay pass.
Recorder input/LP0 are modeled in the CPU/UI run. Held SONG stays dry; coupled
DSP workflow and device placement/packaging remain open. [Results](SKETCH-ARM.md).

2026-10-23 Sketch follow-up: native periodic View updates keep recorder status
current without input. Existing manual capture runs with Sketch open; five real
FREEZE snapshots span both read-only list pages. The existing next-bar capture
also runs with Sketch open and STOP cancels it while preserving the accepted
BUF, snapshots and all track assignments. 125 scoped BUF tests, 24 capture/list
checks, the 20-check no-recording panel run, stock Song opt-out and independent
SINE replay pass. A final native layout probe checks the raised footer labels
without another capture. These are CPU/UI observations with modeled input, not
DSP audio or hardware qualification. SONG ARM/FREEZE remain dry; backend,
preview, persistence and memory policy are unchanged. [Results](SKETCH-UI.md).

2026-10-23 Sketch stages 1–2: separate opt-in native View/scaler over the
unchanged BUF backend; SONG release toggles, FUNC+SONG logs dry ARM, held SONG
logs dry FREEZE/refusal. One volatile BUF preference is independent of recorder
DEST=NORMAL; SRC/CHAN/LEN/MON use stock accessors. Native panel, filename-modal
ownership, stock Song opt-out, 175 BUF/core tests and final stable-source SINE
replay pass. No capture/job/assignment/save from the dry controls. Native bitmap
captures are available; populated frozen lists, capture while Sketch is open,
backend action integration, preview, persistence and hardware remain outside
this result. [Controls, ownership, results and screenshots](SKETCH-UI.md).

2026-10-22 BUF continuous reuse: 13 consecutive native one-bar publications
while a pattern plays, shared BUF 1 on T1/T5 and frozen A on T6. Eleven native
releases and ten extent reuses leave 904 KiB DSP storage and identical settled
CPU heap free space at checkpoints 2–13. IDs remain unique beyond eight; no
allocator/ID-limit change. All 15 capture attempts were consumed: an initial
heap-ledger assertion, then 13 successful publications and a final capture
stopped by an AMP no-op assertion. Raw runs stay failed; final harness fixes
are prepared-boundary checked, without another recording. Saved-page ONESHOT
and REPITCH PCM comparisons pass; REPITCH retirement and hardware remain
unqualified. The all-ONESHOT guard is unchanged. [Results](BUF-CONTINUOUS.md).

2026-10-22 BUF architecture alignment: the [canonical contract](../BUF-WORKFLOW-CONTRACT.md)
supersedes the older assigning/seed-take prototype below. Native next-bar recording
uses global recorder DEST, initializes empty BUFs, preserves track assignments,
permits ordinary performance edits and refuses unsupported R.LEN values.
The empty/shared-BUF CPU flow passes with actual parameter changes and full-rate
modeled input; independent saved-publication DSP comparisons preserve old/frozen
readers. A short native retirement run frees/reuses one physical extent with a
fresh identity. BUF/Flex scoped units pass (192 combined, 115 default BUF).
The continuous coupled run remains failed in its SEC-state clone comparator;
that comparator was removed from the final driver. Full-bar publication takes
189–195 ms in the model and misses the following bar's first trigger. Empty-row
labels, broader playback/retirement compatibility, persistence and hardware
remain open. [Results and next steps](BUF-WORKFLOW-ALIGNMENT.md).

The following entries retain earlier milestone evidence and test counts.

2026-10-22 test organization: BUF and existing Flex have separate source guides
and scoped unit commands. `./labctl unit` defaults to 110 native BUF/recorder
tests; `./labctl unit flex` selects 92 Flex/recorder tests. Older BUF models,
Capicola, Arp, integration and core tooling are separate groups. All 428 original
test IDs remain available; six test-selection checks bring explicit `unit all`
to 434. Current BUF tests share a fixture helper rather than importing each
other's test classes. No firmware/DSP code or feature builders changed.
The 110 BUF and 52 core tests pass; full-suite collection preserves all original
IDs without running unrelated feature suites. Audit:
`out/runs/buf-test-housekeeping-20261022-01/verification.json`.
[Feature guide](FEATURES.md), [testing policy](TESTING.md).

2026-10-22 BUF native next-bar capture: SAMPLING+YES on an initialized BUF records one native bar, waits for original normalization/loading, and automatically USEs the take while the pattern continues. Final coupled flow passes first-step alignment, 56,480-frame capture/page equality, frozen A preservation, 12,858 exact stock-voice blocks and two independent stock-file renders. Same-source missing-clock/STOP-cancel controls, 13 focused tests, all 428 unit tests and SINE pass. Earlier clock-value and one-step phase candidates are retained; the first coupled candidate was interrupted before qualification. DSP, normal builders and Flex R5 are preserved. Fixed one-bar normal 16-step/all-ONESHOT emulator slice; configurable lengths, broader clock/project lifecycle, native feedback/save, shipping placement and hardware remain open. [Results](BUF-NEXT-BAR-RESULTS.md).

2026-10-22 BUF performance: separate ONESHOT emulator adapter adds native SAMPLING+C FREEZE of the selected track's BUF while a pattern plays. A four-take record/trim/USE flow passes 14 native note triggers, stop/restart, two automatic releases, retained frozen A/current D, 9,393 exact stock-voice blocks and two independent stock-file oracles. 415 unit tests and SINE pass; native payload/adapter bytes match that SINE run, with panel setup/evidence corrections only in the later driver. The failed zero-note fixture is preserved. DSP and existing Flex R5 are unchanged. Next-bar capture, automatic USE, native BUF saving, device feedback/timing and hardware remain open. [Results](BUF-PERFORMANCE-RESULTS.md).

2026-10-22 BUF automatic cleanup: separate opt-in emulator adapter, preserving existing Flex R5 and normal builders. Native GUI policy selects obsolete versions, skips current/frozen roots, throttles retries and yields to recording/FREEZE. One four-record panel scenario passes retained-reader timeout and automatic recovery, two native releases, 7,493 exact stock-voice blocks and two independent stock-file renders. 406 tests and SINE pass; DSP is byte-identical. Native BUF readback/SAVE, shipping placement, running-sequencer policy and hardware remain open. [Results](BUF-AUTO-RETIREMENT-RESULTS.md).

2026-10-20 Flex RAM-bank save R5: stock filename editor → visible bank A–H → save with exact slot preview. Current bank/slot is the default; cancellation, full banks and failed/unready loads/writes preserve the take. Selected-track relocation retains machine controls and old-slot aliases. Exact-package panel, original project save/independent stock reload, Discard, native reset, 281 tests and SINE regression pass at their documented evidence layers. DSP remains byte-exact to R4; physical R5 operation is unverified. [Results, OS and screenshots](FLEX-BANK-SAVE-RESULTS.md).

2026-10-19 Flex project-save R4: a stale temporary reference reproduced ERROR before the stock project writer. R4 preserves missing references and saves other project contents, while retaining live-take persistence failure guards and exact tombstone matching. 266 tests, native save/stock reload/fresh-runtime save, reset and repeat packaging pass. The GUI reaches DONE with an explicitly modeled SHA-256 boundary. The user reports successful installation and Save Project As into a new project on hardware; hardware reload, power-cycle persistence and broader Flex testing remain unreported. [Results and OS](FLEX-PROJECT-SAVE-FIX.md).

2026-10-19 Flex discard R3 cleanup: user-requested immediate discard on the first YES release, with the confirmation screen and UP/DN hint removed. Existing discard memory/persistence handling is unchanged. [Results and screenshots](FLEX-DISCARD-CLEANUP-RESULTS.md).

2026-10-19 Flex discard R2: professional native save/discard menu with waveform icon, explicit confirmation and busy-reader protection. Discard tombstones the take, clears current aliases through stock unload and frees its CPU source without writing a file. Issued IDs are not recycled. Exact-package native T9 UI, original project writer and independent stock reload, 262 tests, reset/depacker and default/DSP parity pass. [Results and screenshots](FLEX-DISCARD-RESULTS.md). Hardware discard remains unverified.

2026-10-19 Flex save screen: optional native SAMPLING save page for the selected
track's unsaved take, independent of the six stock sample playback machines.
Manual/armed recording and USE overwrite guards, selected-track USE, native
cancel/failure/naming/save flow and independent exact PCM reload pass. Packaged
screenshots, 255 source tests, reset/canaries, actual MAIN depacker and SINE pass.
Default any-track MAIN and accepted DSP remain byte-exact. No hardware transfer.
[Results and actual screenshots](FLEX-SAVE-SCREEN-RESULTS.md).

2026-10-19 stopped arp: a separate `--arp-stopped` all-feature candidate plays
held track-1 keyboard notes with PLAY off at the native tempo/rate. Original
STOP cleanup remains. The packaged stopped/recording panel checks, native reset,
CAPI controls, actual bootstrap depacker, 240 source tests and SINE pass. Default
R2 and candidate DSP remain byte-exact; 28 code bytes added with no new state.
[Results and candidate](ARP-STOPPED-PLAYBACK-RESULTS.md). New hardware/timing and
full coupled startup remain unverified; resource monitor is not included.

2026-10-17 CAPI R2: actual MAIN depacker reproduced a265,885-byte overflow in the withdrawn build. Equivalent ADI zero-fill encoding reduces the DSP stream to626,332bytes with422,243bytes headroom. Entire loaded memory and MAIN remain exact. Actual MAIN canary tests, host/native audio, stereo/Plaits/final-ring, repeated reset/bootstrap,235tests and SINE pass. [Replacement and results](CAPICOLA-REDDIT-BOOT-FIX-RESULTS.md). Physical confirmation pending.

2026-10-17 hardware failure: initial author CAPI candidate a70f91d7 is withdrawn. Stock CPU DSP-stage overflow identified; [local repair](CAPICOLA-REDDIT-BOOT-FIX.md) in progress. Earlier passing emulator checks did not cover the actual MAIN depacker allocation.

2026-10-17 author-release CAPI replacement: the shared dt2-capicola release-default engine now replaces the old backend in `--all-features`. The pinned source, SHARC stereo/search paths, memory relocation, binary switch, unchanged CPU image and exact validation results are documented in [results](CAPICOLA-REDDIT-RESULTS.md). Earlier entries below describe preserved historical candidates.

2026-10-17 CAPI UI: [stock binary switch](CAPICOLA-SWITCH-RESULTS.md) replaces the encoder dial in the new all-feature source-playback package. Native OFF→ON→OFF UI/storage/transport checks and 230 source tests pass. Two MAIN bytes change; DSP is identical. No hardware transfer.

2026-10-17 Capicola source playback: new source-first reader/dual-grain handoffs and native stereo,32channel banks within existing8MiB.504full-start upstream comparisons, actual KeyframeRecorder pair,36packaged reader cases, native stereo/trigger/routing/final-ring checks, repeated DSP reset/depacker,230source tests and SINE pass. MAIN/default exact. Fidelity prioritized over emulator instruction allowance; physical listening/deadlines remain open. [Results](CAPICOLA-SOURCE-RESULTS.md), [verification](CAPICOLA-SOURCE-VERIFICATION.json).

2026-10-17 CAPI quality candidate: a guarded optional source overlay replaces
the prototype's 20 ms adaptive-fade cap with content-dependent spans, selected-
region guards and bounded float32 phase progress. Nine actual original-Granule
host/packaged SHARC comparisons pass (target maximum error below 2.4e-7);
the old capped reader fails the six splice cases. Host boundary/control cases,
120 target boundary cases, phase termination, sixteen-bank routing, final-ring
causal mute, repeated DSP reset, actual bootstrap depacking, 228 source tests
and stable-source SINE pass. MAIN and the default all-feature package stay
byte-identical. No lane/bank storage grows; longer two-head fades cost more
DSP work in the measured fixtures. Physical A/B, timing and headroom remain
open. No hardware transfer, commit or publication occurred. [Results and
reproduction](CAPICOLA-QUALITY-RESULTS.md),
[verification](CAPICOLA-QUALITY-VERIFICATION.json).

2026-10-17 all-feature OS: an actual local OS 1.16 `.syx` now combines
Plaits R3, CAPI time stretch OFF/ON, native Arp tempo/rates and managed Flex.
Plaits keeps its reviewed CPU placement; a separate 54-byte loader initializes
the same Arp/Flex DDR payload. CPU reset/ready, native controls, repeated DSP
reset, sixteen-track DSP playback, Arp-to-Plaits voice replay, twenty-second
stereo Flex lifecycle and a single Arp/Flex GUI save/recall session pass.
The latter preserves 121,740 pattern bytes, settings, exact recorded-note
replay and native sample/transfer equality. A cache-hit observer error was
corrected and the complete GUI scenario rerun; all guest image bytes stayed
identical. All 226 source tests and stable-source SINE pass. CAPI starts OFF;
encoder C on STRETCH enables it. Existing feature limits remain. Coupled
CPU/SHARC cold boot, physical timing/cache ownership and hardware behavior
remain unverified. [Build and reproduction](ALL-FEATURES-EXPERIMENT.md),
[verification](ALL-FEATURES-VERIFICATION.json). No commit, publication or
hardware transfer occurred.

2026-10-17 CPU extension: an opt-in stock OS 1.16 image now places Arp and
managed Flex in one 64 KiB DDR reservation, with a 54-byte reset loader and
one phased project-save hook. Native reset reaches ready and executes 39
stock heartbeat calls into DDR; segment/BSS/canary checks and the disabled
loader negative pass. Prepared-fixture Arp record/save/recall/exact replay,
20-second stereo Flex lifecycle, 223 source tests and stable-source SINE pass.
Standalone image hashes and stock DSP are preserved. Dense placement exposed
and corrected an incomplete bitmap descriptor in the experimental layout.
Both-active combined persistence, coupled startup and physical ownership/timing
remain open. [Notes and reproduction](CPU-EXTENSION-EXPERIMENT.md),
[verification](CPU-EXTENSION-VERIFICATION.json). No commit, publication or
hardware transfer occurred.

2026-10-16 reuse: shared CPU emission/placement, build context, family-driven
DSP compilation, typed hook contracts, replay I/O and native phased project
save helpers are implemented. Default active CPU/DSP builds reproduce frozen
bytes; 217 source tests, SINE replay, optional Arp/Flex save lifecycles and paired
STRETCH state/master/ring checks pass. Optional cache/trace specialization saves
1.33% of mean emulated block instructions in the paired steady fixture and
0.95% during rapid edits. This is not physical utilization. Arp/Flex composition
is explicitly refused because current code placement overlaps and does not fit;
the shared save entry does not resolve that limit. See
[reuse results](REUSE-RESULTS.md) and its verification record. No firmware was
sent to a device and nothing was committed or published.

2026-10-16 G sensitivity: the user reports the arp is almost perfect on the
device and requests a slower G response. R2 reuses the stock Keyboard Settings
encoder scaler and existing view state, filters tiny movements and avoids
unchanged-value redraws. It adds no state allocation, timer or hook; the fixed
8 KiB state remains. Focused native checks, the source regression suite, actual
panel selection/120 BPM UP recording and bounded startup pass. Package loader
checks and artifact details are recorded in [G sensitivity](ARP-G-SENSITIVITY.md).
The new knob feel still needs a device trial; nothing was uploaded or committed.

2026-10-16 arp: the user now reports the previously installed arp works as expected; its exact hash and delayed-start cause remain unconfirmed. A separate native tempo/rates continuation follows the stock tempo getter, adds quarter/eighth/sixteenth/32nd rates and G push focus. Native timing, real Tempo-menu input, 127.5 BPM eighths, 300 BPM 32nds and packaging/startup checks pass; recording, native menu save and checkpoint-resumed menu recall/replay now pass, including exact pattern preservation and mode/rate restoration after clearing RAM. See [tempo/rates results](ARP-TEMPO-RATES-RESULTS.md). New-candidate hardware remains unverified.

2026-10-15 arp diagnosis: re-entering keyboard mode did not resolve the user
report; installed candidate is not yet confirmed. The optional D1 build exposes
held/PLAY/stock-keyboard/sample-clock/API/output counters for the next device
observation. It does not claim another fix. Default MAIN bytes stay identical
to the keyboard-fix build. See [D1 diagnostics](ARP-STOCK-FIRMWARE-RESULTS.md#d1-device-diagnostics).

2026-10-15 arp hardware follow-up: the user reports no arp on T1 with UP and held keys, stopped or playing. The first native package therefore failed its device trial. A stale private keyboard-mode flag reproduces the symptom in an explicit emulator mismatch fixture; the follow-up reads the live stock setting. The physical cause and replacement hardware result remain unconfirmed. See [arp follow-up](ARP-STOCK-FIRMWARE-RESULTS.md#hardware-failure-follow-up).

2026-10-15 native arp: [Stock-only OS 1.16 firmware](ARP-STOCK-FIRMWARE-RESULTS.md) now replaces the Python arp services with native G control, keyboard ownership, task clock and AR16 journal I/O. UP records, saves, recalls through the normal project menu and replays its exact notes; all 121,740 pattern bytes survive. Native mode/failure checks, current-source SINE, container/original depacker and bounded startup pass. The private SYX has unchanged stock DSP/protected sections. Track 1 and fixed 102 BPM remain; card-backed power-on recall, broader lifecycle and hardware are unverified. Nothing was flashed or committed.

2026-10-15 arp: [Project load and optimization](ARP-PROJECT-LOAD-RESULTS.md) verifies native G OFF/UP/ORDER/RANDOM, ordinary recorded notes, normal project-menu mode recall and missing/corrupt companion fallbacks in the OS1.16 emulator. Seven imports, exact full patterns, 180 source tests, native audit, unchanged musical/control/overlay bytes and SINE pass. Storage synchronization is incremental and helper stacks are isolated/guarded. Track 1 and 102 BPM remain the bounded scope; hardware and firmware packaging are separate.

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

## Optional CAPI comparison — 2026-10-13

The existing STRETCH machine now has an optional per-track CAPI OFF/ON on
encoder C. Native trigger latching, stock/R3 rendering, mixed sixteen-track
routing, native locks and buffered second-SRC-page feedback pass. The builder
requires `--capi-toggle`; omission reproduces the original combined image.
[Results and reproduction](CAPICOLA-TOGGLE-RESULTS.md). Device timing, coupled
operation, full project persistence and existing lifecycle gaps remain separate.

## Optional any-track routing — 2026-10-19

The optional `--all-features --any-track` build keeps one keyboard arp following
the selected track 1–16, with existing per-pattern settings and stopped playback.
Plaits permissions, controls and independent lane state now cover all tracks.
Capicola already has sixteen-track routing; Flex already accepts compatible
destinations on any track and retains its shared recorder. The previous default
and stopped-arp SYX bytes reproduce exactly. The new candidate remains subject
to the separate physical device trial. [Artifact, checks and remaining limits](ANY-TRACK-FEATURES-RESULTS.md).
