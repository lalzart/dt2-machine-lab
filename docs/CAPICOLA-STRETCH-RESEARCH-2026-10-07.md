# Capicola-derived stretch for Digitakt II

Status: proposed; research complete, implementation not started. 2026-10-07.
Work type: source-reimplementation feasibility. Target: Digitakt II OS 1.16.

## Recommendation

**INFERENCE:** A Capicola-derived sample machine is a credible experiment for our lab. Start with a bounded mono keyframe reader and an upstream C++ oracle, then translate to C99 for SHARC. Keep stock STRETCH available. Do not begin with sixteen tracks, the whole Eurorack module, or a replacement firmware package.

Its performance identity is independent pitch and time control with content-adaptive splices. Fidelity to that source is distinct from reproducing the Reddit author's unpublished integration. This research does not change the existing Plaits priority.

## What the shared link establishes

**EVIDENCE:** [The Reddit post](https://www.reddit.com/r/Elektron/comments/1wyg27f/alternative_stretch_for_digitakt_2/) credits [heavylight-industries/capicola](https://github.com/heavylight-industries/capicola) and reports simultaneous operation on sixteen tracks, while explicitly saying testing and optimization remain. These are the poster's observations, not our hardware or resource measurements. The accessible post does not supply their port's source, firmware version, memory layout, compiler settings, or test conditions. No separate port repository was found in the linked post and bounded web searches. This is not proof that none exists. The demonstration video was not independently auditioned here.

**EVIDENCE:** Capicola is a C++17 DSP implementation for the Alchemy Lab/Daisy platform. Audited main commit: `120b0b843c18bda373d96eb79d49805545f61556`, dated 2026-10-01, commit title “Capicola 1.0.0: bidirectional pitch and stretch, ping-pong gesture”. Upstream source stayed unchanged; only host build output was added to the scratch checkout.

[Matthew Nielsen's paper repository](https://github.com/heavylight-industries/dafx26-paper) describes *Keyframe Time Stretching via Extrema Sampling*. Its abstract reports lower computational cost than PV/WSOLA and names saturation and spectral-contrast loss as artifacts. That is author-reported comparative evidence, not a SHARC benchmark. This review read the abstract and implementation; the PDF fetch failed, so full paper methods and listening results were not verified.

## How the implementation works

**EVIDENCE, source inspection:**

- `Analyzer.h` runs an eight-sample raw ring through a B-spline front end, detects derivative sign changes, estimates fractional peak positions, and stores extrema only when their amplitude difference exceeds a threshold. The significant peaks/troughs become timestamped keyframes.
- `SparseLine.h` stores a power-of-two ring of packed 12-byte records: float amplitude plus double sample time. It supports binary search for positions and walking cached windows. Its enum says CATMULLROM, but that branch actually uses a two-endpoint smoothstep/Hermite blend, not conventional four-point Catmull-Rom. Preserve the implementation when forming an oracle.
- `Granule.h` advances an ideal timing cursor by stretch speed and actual audio cursors by pitch speed. When their distance exceeds a leash measured in keyframes, it crossfades back toward the ideal position. Crossfade length follows the local sample-time span of those keyframes, with boundary rescue rules and a 48-sample adaptive minimum.
- `KeyframeRecorder.h` manages two trading granules. A transient or forced slice can seed a new granule and crossfade from the previous one. In LIVE_EFFECT, an entire input block is analyzed before output is rendered. Detector-trigger decisions are block-level; changing block partition can change behavior.
- `Detector.h` derives events from TKEO energy, smoothing, adaptive thresholding and a default 150 ms minimum event gap. The recorder adds a fade-length refractory period. These are live slicing decisions, not a finished Digitakt slice-marker editor.

Conceptually, `ideal += stretch`, `actual += pitch`; sparse-index separation controls when to splice. Interpolation and takeover weights use `w=p*p*(3-2*p)` and `y=(1-w)*old+w*new`. No FFT or waveform cross-correlation appears in this audited core. This alone does not establish worst-case runtime: window walking and exceptional reanchors remain data dependent.

## Behavior and source boundaries

| Item | Upstream behavior | Proposed treatment |
|---|---|---|
| Pitch/time | Separate signed rates; stretch is source-position advance, not output-duration multiplier | Preserve core math; begin positive rates only |
| Analyzer | Default threshold 0.001 | Preserve first; expose quality only later |
| Grain leash | Default 128 keyframes | Preserve baseline; test 16, 64, 128 |
| Crossfade | Recorder default 2400 samples; module overrides to 960 samples | Freeze 960 at 48 kHz for first oracle |
| Transport | STOPPED, RECORDING, PLAYBACK, LIVE_EFFECT; requests processed at block start | Preserve oracle; explicit sample-machine adapter later |
| STOPPED | Passes input to output | Adapter must define note-off silence separately |
| Playback start | PLAY resets readers, then Punch seats a grain at the delayed latest tap | Cannot assume “play loaded sample from its start” |
| Record end | STOP_REC arms a final keyframe for a subsequent Analyze call | Explicitly test finite-file closure and final frame |
| Stereo | Independent channel engines; when one auto-fires, drift above one second forces the other to slice next block | Exclude first; linked stereo is a deliberate later deviation |
| Shaping/feedback/CV | Optional shaping, module feedback, followers and CV UI | Exclude; `Init(nullptr)` gives clean recorder path |
| Reverse/freeze | Signed rates and direction-change crossfades | Deferred, not claimed equivalent in first experiment |

Initialize before processing; no implicit hardware startup constructors. CLEAR resets sparse storage/analyzer/readers; recorder requests are a single pending slot, not an event queue. Retrigger, panic, sample replacement, project recall, nonfinite recovery, and track independence need explicit adapter rules. Source comments claiming no clicks or no aliasing are not independent guarantees; repeated forced punches and interpolation need measurement.

## Local fit and resource risks

**EVIDENCE:** The machine-lab checkout is on `codex/plaits-macro-controls`, HEAD `c1a0ad675741339c5e154dcb5a58caa7b65b21c2`, with substantial inherited dirty/untracked work. It was preserved. Pinned DigiKit is clean at `277760aad51b036a4756db051409d4d3b1eeccbc` (detached HEAD; origin m-dwyer/digikit); Selache is `2b26d3b75c53063575bc5c820fa0d38879335187`. No dependency was updated. Existing [Plaits VA](PLAITS-VA.md) and [integration notes](INTEGRATION.md) supply the C99-to-SHARC and prepared replay precedent. Current [status](STATUS.md) additionally records a user hardware listening result for Plaits R2 on track 1; that is not Capicola evidence.

1. **Memory:** The module uses 2^21 keyframes/channel: exactly 24 MiB/channel, 48 MiB stereo before other state. Sixteen copies would be 768 MiB of keyframe arrays. Those are configuration arithmetic, not DTII free-memory measurements. A proposed 4096-frame mono ring is 48 KiB; stereo sixteen-track replication is 1.5 MiB before state. Usable duration depends on signal density: a 1 kHz sine is roughly 2000 extrema/s, whereas noise/high-frequency material consumes frames much faster. Sparse storage is not guaranteed compression over PCM.
2. **Numeric/toolchain:** The source uses templates, lambdas, std::array, packed records, double positions and 64-bit monotonic indices. Our route is C99. Selache exposes double-size options and wide-integer support, but correct, efficient execution of this exact workload is untested. Do not silently replace double positions with float: integer-sample precision is lost after 2^24 samples (about 350 s at 48 kHz), with fractional precision degrading earlier. Bounded/rebased positions are a possible intentional redesign.
3. **Rate/block adapter:** Upstream module is 48 kHz/64 frames; the prepared DTII voice hook is 96 kHz/64 samples, exported as 48 kHz/32. Preserve a 64-frame source oracle, then evaluate a 32-frame variant separately. FIFO scheduling or a new native-rate contract is needed; changing block size is not automatically equivalent. Detector and 48-sample/50 ms constants require attention if sample rate changes.
4. **Sample access:** Plaits generates sound; this engine needs actual selected-sample data. Choose preanalysis on load or a bounded streaming keyframe cache with lookahead. Both need ownership, sample replacement, start/end/loop behavior and cold-start handling. Current Flex recording-to-ONESHOT work does not supply these automatically.
5. **Stereo and load:** Independent grain schedules may move a stereo image. A sample machine may require linked decisions, tested with identical L/R, anti-phase and asymmetric transients. Retired emulator instructions and Mac test speed cannot establish physical DSP deadline margin, especially with all tracks/effects running.

**UNRESOLVED:** Free safe SHARC memory, code placement, double/wide-integer cost, worst-case cache refill, sample-loader seam, parameter storage, exact stock stretch semantics, and coexistence with the current Plaits/Flex image.

## Dependency and license boundary

**EVIDENCE:** The core is AGPL-3.0 per the repository LICENSE, not MIT. `KeyframeRecorder.h` includes Analyzer, Granule, Detector and Shapers; their closure reaches the eleven local headers recorded in the source manifest plus standard C++ headers. No Daisy SDK is needed for the host test build. The excluded board integration references SDK gitlink `0cd2518c66a3f410507d202de274c2832cb4d6ee`; upstream describes SDK/libDaisy as MIT, but those uninitialized submodules were not independently audited.

The research uses an unchanged public checkout and runs its tests. Preserve author attribution and license notices in any later source port. **UNRESOLVED:** licensing/distribution compatibility of a combined derivative with proprietary firmware; this note does not establish permission to distribute such a package. The paper's CC-BY license is distinct from the code license.

## Verification actually performed

The host-only CMake branch was inspected before execution. The Ninja preset failed because Ninja is unavailable; no tool was installed. The following fallback succeeded with AppleClang 16.0.0.16000026:

```sh
# From an unchanged checkout of the pinned Capicola revision:
cmake -S . -B build-host-make -G 'Unix Makefiles' -DCMAKE_BUILD_TYPE=Debug
cmake --build build-host-make
ctest --test-dir build-host-make --output-on-failure
./build-host-make/tests/host/capicola_tests
```

**EVIDENCE:** CTest 1/1 passed. The executable reported **279171 checks, 0 failures**, covering sparse rings, analysis, detectors, granules, recorder operation, reverse motion, trigger timing and a bounded hostile-input fuzz test. Reported sine reconstruction NRMSE: 0.0190; unity live RMS: 0.693 versus analytic sine 0.707; fuzz worst absolute output: 0.995. This is upstream test coverage on the Mac, not a new independent quality comparison. The offline renderer compiled, but no render/listening comparison was performed.

Retained [host log](../out/research/capicola-2026-10-07/upstream-host-tests.txt) and [source hashes](../out/research/capicola-2026-10-07/source-manifest.json) are ignored local artifacts. Every examined core header and the upstream test are SHA-256 pinned there. No DSP source, firmware, runtime adapter, existing document or dependency was changed; only this proposal and research evidence were added.

## Smallest useful experiment, if requested later

**HYPOTHESIS:** A bounded mono reader can preserve upstream behavior on SHARC at a useful resource cost. First distinguish source equivalence from a new finite-sample transport.

1. Freeze the source manifest and an implementation-ready contract. Run `./labctl doctor` before firmware work and fingerprint the exact reused hook/compiler binaries. Retain the current known-good Plaits/Flex output.
2. Build an unchanged C++ oracle around Analyzer/SparseLine/Granule with a specified fixed sample and explicit start cursor. Translate only that path to C99. Use 4096 keyframes initially, fail clearly on preanalysis overflow; do not silently truncate or raise threshold. No module UI, SDK, distortion or feedback.
3. Fixed initial conditions: 48 kHz, 64-frame blocks, 1-second input, 128-frame leash, threshold 0.001, 960-frame fixed fade. Deterministic signals: silence, impulse at sample 4800, 220 Hz sine, two-tone 220/331 Hz, and generated noise with explicit xorshift32 seed 1. Test pitch 0.5/1/2 and stretch advance 0.5/1/2. Render two seconds per case; finite-end behavior must be specified identically for both implementations before coding. Store raw float output, trace, WAV, parameters and hashes.
4. Require repeat-exact host output and matching state/event traces. Initial host C99 acceptance target is bit-identical output under matching arithmetic options. Proposed SHARC error limits: max 1e-4 and RMS 1e-5 versus oracle for these short vectors; freeze these before implementation and investigate failures rather than widening limits automatically. Every sample must be finite. Independent instances must not affect one another; capacity overflow and unsupported parameters must be explicit failures.
5. Measure worst block instruction count, state/code bytes and cache-refill work before integrating one track. Compare native compiled output with the oracle, then test track selection, trigger, stop, sample replacement and stock-machine negative controls. Add actual firmware transport only after the core result.
6. For musical comparison, use the same authorized drum loop, bass, voice and dense mix through stock STRETCH and the candidate at 0.5x/0.75x/1.5x/2x duration and ±12 semitones. Keep raw outputs, use separately loudness-matched blind audition copies, and inspect onset smearing, pitch error, stereo correlation, clicks and spectral changes. Unity operation is not assumed PCM-transparent. No quality verdict until this is done.

A direct port remains the best source-equivalence baseline. Preanalyzing an entire sample can share immutable keyframes between voices but requires a new finite-file transport and memory policy. A rolling cache saves space but makes seek/reverse/refill scheduling harder. These are design choices to test, not facts about the Reddit port.

## Decision and evidence limits

Recommended next scope: **one mono sample, upstream oracle, C99 core, standalone SHARC comparison**, followed by one DTII track only if that passes. Keep old STRETCH as a separate selectable behavior; assign no new machine ID until compatibility is checked. A linked stereo policy, compact/rebased timestamps, finite-sample transport and a new UI are intentional deviations requiring their own contract.

Research and upstream host verification are complete. No port, SHARC build, firmware package, real-time test, hardware test or listening verdict exists for this candidate. Approval and implementation bundle are not yet present; that is appropriate for the user's research request. Physical testing and publication remain separate decisions. The strongest open question is the cost and correctness of sample access plus sparse state on the actual DTII execution path, not whether the C++ source can compile on the Mac.
