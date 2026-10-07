# Next Digitakt II machine: comparative research

Date: 2026-10-07. Status: proposed; research complete, no implementation begun.
Target: Digitakt II OS 1.16. Digitone means **Digitone II**, not the original Digitone.

## Recommendation

**Engineering judgment:** prioritize **Digitone II FM Drum**, with **Swarmer** as the complementary second engine. Investigate both renderer boundaries before choosing which to implement first. FM Drum has the strongest musical fit; Swarmer is the simpler independent-design fallback, not a proven easier binary transplant.

For the older instruments, prioritize **Monomachine FM+** or **Machinedrum EFM** if their particular sound is the goal, and **VO-6** if maximum contrast with our existing Plaits bank matters most. These involve cross-architecture translation or a new implementation, not straightforward relocation.

This note delivers candidate selection, source availability, integration risks and a bounded next experiment. It does not authorize or perform a firmware edit, download of donor firmware, hardware test, commit or publication. Musical-interest scores below are judgments, not listening-test results. A working deliverable for this turn is this research note, at catalog/proposal evidence level.

## Current baseline, refreshed from the workspace

**EVIDENCE:** The preserved DigiKit checkout is on `codex/dt2-sine-machine`, HEAD `277760aad51b036a4756db051409d4d3b1eeccbc`, with local SINE changes. Machine lab HEAD is `c1a0ad675741339c5e154dcb5a58caa7b65b21c2` with substantial later uncommitted work. Both working trees were inspected and preserved.

The [R2 observations](PLAITS-R2-HARDWARE.md) record the user's successful hardware boot and good-sounding Plaits models/controls on **track 1**. [R3 results](PLAITS-INTEGRATION-R3-RESULTS.md) add emulator/compiled-DSP checks for named models, duration and LFO destinations; they do not establish an R3 hardware result. [Current status](STATUS.md) also records later Flex work. The 2026-10-05 [Digitone feasibility note](DIGITONE-II-FEASIBILITY.md) predates these advances: its blanket control/playback limitations must not be treated as current.

The bank already includes VA, two-operator FM, analog bass drum, waveshaping, additive and granular-formant synthesis. A generic oscillator or another basic kick therefore adds less than an engine with a distinct articulation/control system.

## Candidate comparison

**INFERENCE:** Difficulty refers to one useful monophonic track. “Recreation” means independently implementing documented behavior; “original” means preserving the original renderer. No candidate has a measured DTII port cost yet.

| Candidate | What it adds to DTII | Reduced recreation | Original-code route | Priority |
|---|---|---|---|---|
| DNII FM Drum | Synthesized percussion with substantially more articulation than the current basic FM/BD models; lockable changes between hits | Medium–high | Plausible SHARC relocation; setup, envelopes, tables/transients and control conversion unresolved | First musical choice |
| DNII Swarmer | Detuned, animated ensemble sound for bass, drones and stabs | Medium | Same-architecture candidate; actual dependency size unmeasured | Second engine / simpler fallback |
| DNII FM Tone | Deeper melodic FM and evolving struck tones | High | Same architecture, but operator state, envelopes, routing and controls need closure | Later; strongest if melodic FM is the priority |
| DNII Wavetone | Broad wave shaping and sync textures | High | Same architecture, with table and discontinuity-handling dependencies | Later; more overlap with existing VA/WS |
| MD EFM, initially one BD or XT voice | Compact percussion controls and the older digital character | Medium–high | DSP56300-to-SHARC translation; coefficient generation matters too | Best older-drum starting point |
| MD TRX, initially BD or SD | Immediate traditional drum synthesis | Medium for an approximation | Same cross-architecture problem; exact sound is more work | Useful, but less additional range than EFM |
| MD P-I | Tuned resonant percussion | Medium–high | Stateful physical-model code, delay memory and original arithmetic | Interesting specialist follow-up |
| MM FM+ STAT/PAR, then DYN | Metallic and unstable pitched/percussive timbres with compact controls | Medium–high | Translate DSP56300 semantics; isolated-track reference now available | Best Monomachine engineering shortlist |
| MM VO-6 | Articulated synthetic vocal percussion and syllable sequences | High for full articulation | Original renderer plus formant/envelope/control dependencies | Most distinctive longer-term choice |
| MM SID | Chiptune-like articulation, sync/ring interactions | Medium for inspired voice | Accurate legacy behavior and cross-track modes raise cost | Lower priority unless this sound is wanted |
| MM DigiPRO / SuperWave ensemble | Digital waves and single-track chord textures | Medium–high | Wave assets, interpolation, chorus and source arithmetic | Worth revisiting after FM Drum |

Behavior references: Elektron's [Digitone II manual, OS 1.10B, Appendix A/B](https://www.elektron.se/wp-content/uploads/2025/06/Digitone-2-User-Manual_ENG_OS1.10B_250609.pdf), [Machinedrum manual OS 1.63, Appendix A](https://www.elektron.se/wp-content/uploads/2024/09/machinedrum_manual_OS1.63.pdf), and [Monomachine manual, Appendix A](https://www.bhphotovideo.com/lit_files/85386.pdf) (Elektron-authored, distributor-hosted). FM Drum combines FM, pitch movement and transient/noise shaping; Swarmer combines a main oscillator with six detuned oscillators. VO-6's consonant/vowel articulation is materially different from merely having a formant oscillator.

I would deprioritize MD E12/ROM and MM BeatBox as new-machine projects: sample playback overlaps with the Digitakt's strengths. Sampling their output can be useful, but does not reproduce continuously modulated synthesis. Likewise, moving a source generator alone does not reproduce the donor's filters, distortion, effects or routing.

## What “port the code” actually involves

### Digitone II: the most credible original-code route

**EVIDENCE:** DTII and DNII use SHARC+ DSP code. The [external reverse-direction ONESHOT report](https://github.com/angellinares/dn2_firmware_explore/blob/249876bbd4cd85e06c345a5639596aa2e58e1aac/docs/dt2-machine-port.md) reports an offline DTII 1.16 renderer relocation into DNII 1.11: four functions, 611 instructions, two tables, ten relocation sites and exact comparisons for four playback modes. The implementation was removed from that public repository; the report remains. This was not reproduced here and is not a DNII-to-DTII result.

**INFERENCE:** This precedent makes a bounded original-renderer experiment worthwhile. It does not imply that FM Drum or Swarmer is similarly small. We need the renderer, initialization, coefficient conversion, constants/assets, call graph, indirect calls, globals, state layout and rate/block contract. Donor CPU-side parameter mathematics may be as important as DSP code. Similar function shapes do not establish a shared voice interface.

Target donor **DNII 1.11**; behavior manual **1.10B**, with the prior note also referencing **1.10D**. DigiKit's inspected device manifest expects donor SYX SHA-256 `2af43e65e3d8390b41c9f66222620f8cce027d73ed87db00c80b440f628472e0`. DTII 1.16 expected SYX is `278541e466edcd77d6b3e018a91fb90185932d3c7de224dd3e68294dddf3a9ec`. These are inspected expected identities, not freshly rehashed firmware in this research turn. Reauthenticate actual inputs before any experiment. Older DNII 1.10E/DTII 1.15C addresses are not reusable.

### Machinedrum and Monomachine: useful reference tools, different instruction set

**EVIDENCE from source inspection:** [Monomodule](https://github.com/shnolk/monomodule/tree/eb5cfeee2a662d8b6c3d87aeaed6c80b7a995310) separates a host control model from an emulated DSP56303. `DspEngine.cpp` sends 52-word parameter blocks masked to 24 bits; the documented harness returns 16 stereo frames. Its `mnm-render` tool can serve as a candidate offline oracle using OS 1.32B. It is not a C++ implementation of the individual oscillator algorithms. Its documented substitute Digibank and delay limitations prevent treating every output as exact hardware truth.

[Machinemodule](https://github.com/sd88me/mpc-vst-machinedrum/tree/796ded62c7dd2716120cc33a3617950b83b73eab) similarly executes original MD OS 1.63 DSP code. `VoiceEngine.cpp` uses DSP56303 peripherals and extracts 32-sample voice blocks. Its author reports ARM recompilation and a translated mixer, while machine coefficient routines still use emulated main-CPU code. The documented ROM and TRX-SD comparison gaps matter when selecting an oracle. The translated mixer is not translated voice synthesis.

**INFERENCE:** Neither project's executable can be linked into our SHARC machine. Viable paths are semantic translation of one closed renderer, or an independent behavioral recreation. Translation must preserve fixed-point scaling, wide accumulators, rounding, saturation, wrap, address modes, table indexing and scheduling wherever they affect sound. Converting everything to float may make a useful instrument but is not automatically a faithful port.

A whole DSP56300 emulator inside the DTII is a poor first strategy: it adds instruction emulation, foreign state and control plumbing before sound design, with no measured DTII headroom. ARM/x86 JIT speed and MPC results do not predict SHARC cost. A narrow static translator could eventually be useful, but its first target should be one measured routine.

### New community work worth retaining

[Kitbasher](https://github.com/etcetc000/kitbasher/tree/44f5da9c34cddd75690ebbf258d07141c5772dc6) provides original/community Machinedrum models. Its [model inventory](https://github.com/etcetc000/kitbasher/blob/44f5da9c34cddd75690ebbf258d07141c5772dc6/docs/MODELS.md) distinguishes editable source from compiled-only packs. Inspected `examples/community/efm4op/dsp2.asm` is Motorola assembly, not portable C. The compiled synth pack does not provide rebuildable source or demonstrated DTII portability. Thus social posts about Monomachine-like machines on Machinedrum do not settle our port.

Editable models have declared licenses (mostly GPL v3-or-later; the string model MIT). Monomodule/Machinemodule declare AGPL licensing; their emulator dependency is GPL. Original firmware remains separately supplied. No dependency or code was incorporated here; any reuse needs a file-level license/provenance check. These are source-audit facts, not a distribution clearance.

## How the engines would fit into Digitakt II

**Proposed product thesis:** put a compact, expressive percussion synth beside samples, using the Digitakt's existing pattern workflow.

Start with track 1, as in the successful Plaits path. Preserve Plaits as a selectable option. New stable engine IDs, descriptor/range/default handling, dispatch and project representation need explicit design; another engine is not simply another copied menu row. Multi-track state allocation is a separate expansion.

The intended audio path is `trig + locks/LFO → engine state → source buffer → existing track processing → mix`. Verify the downstream chain for the new engine. Our [integration note](INTEGRATION.md) records 64 source samples at 96 kHz and a stock decimation continuation; donor rates and frames must be measured and adapted, not guessed from converter specifications.

Suggested compact first-page controls (design proposals, not original parameter maps):

| Engine | Eight controls |
|---|---|
| Reduced FM percussion | Tune, decay, FM ratio, FM depth, pitch sweep, fold, noise balance, transient balance |
| Swarmer-inspired voice | Tune, duration, waveform, detune, animation rate, animation depth, noise modulation, level |
| MD EFM / MM FM+ faithful attempt | Prefer the donor's native eight synthesis slots; retain independent DTII track controls where supported |

A full FM Drum transplant needs additional parameters/pages or explicit fixed defaults. Eight macros do not expose the full donor. Discrete selections should latch on triggers; continuous modulation needs documented smoothing and transport. Save/reload, lock restoration, LFO updates, retrigger/release, switching and silent reset must be checked independently. Existing stereo lanes do not grant polyphony. A chord oscillator can produce fixed-interval stabs without a polyphonic note allocator, but it still costs multiple oscillators.

**UNRESOLVED:** per-engine code/table/state sizes, owned runtime memory and physical worst-case cycles. Existing loader space is not measured spare memory. Retired emulator instructions are useful for comparisons, not a hardware load percentage.

## Smallest next experiment

This is a research proposal, not an implementation-ready DSP contract. No exact synthesis equations are specified because no independent engine has been selected; cultural borrowing and novelty claims are outside this port comparison.

1. Run `./labctl doctor`, rehash DNII 1.11/DTII 1.16, and capture one deterministic original **FM Drum** voice plus one **Swarmer** voice. Record initialization and all control/state dependencies, code/data sizes, sample rate and block length. Choose by measured closure, not oscillator count alone.
2. For the selected engine, test isolated private relocation against the donor before adding panel pages. Conditions: silence, note-on, sustained parameter change, retrigger, release, two independent states and repeated initialization. Fix random state explicitly. Require identical source PCM for pure relocation; any non-exact numerical/rate adaptation needs a separately declared tolerance.
3. Only after equivalence, connect one DTII track. Keep stock-hook parity, disabled-hook controls and the existing SINE/Plaits regressions. Check controls through the late CPU repack, continuous PLAY, save/reload and machine switching.
4. Compare matched musical phrases with the current Plaits FM/BD/VA. For drums, use a 16-step pattern with pitch/decay/timbre locks and retriggers; for Swarmer, compare sustained and staccato notes with animation. Level-match audition files. Decide whether the added range and playability justify another engine.

Retain `donor-reference.f32`, `candidate.f32`, `dependencies.json`, `controls.json`, per-block profiles and `report.json` under one uniquely named ignored `out/runs/` directory, including failures. Freeze exact timelines, seeds and tolerances before coding. Hardware timing and final-output listening remain later, separately requested checks.

**Pivot:** if setup depends on a large donor scheduler, unexplained shared globals, or an unclosed call graph, stop the relocation attempt and price an independent engine. For an older-machine experiment, choose one EFM or FM+ routine and establish an integer reference first; do not begin by porting a whole device.

**Planning scale, not an estimate backed by measured closure:** reduced original-design voices are days-to-weeks work with this harness; polished controls, lifecycle and persistence are weeks-scale or longer. A faithful DSP56300 translation is a substantial additional project. Original DNII relocation cannot be responsibly scheduled until the first dependency audit; no hardware-ready deadline is asserted.

## Research provenance and limits

Inspected active README/EMULATION/AGENTS guidance, machine-lab status, hardware observations, integration notes, source-level external adapters and the pinned repositories above on 2026-10-07. Official manual PDF retrieval was intermittent; the 1.10B PDF was readable and its FM Drum architecture and controls were checked directly, alongside the existing versioned feasibility note. Public repository claims were not independently executed. No completed DNII-synth-to-DTII or MD/MM-to-DTII port was established in this bounded search.

Only this note was created. No DSP tests were rerun because no implementation changed. The next decision is which measured renderer boundary to pursue, with **FM Drum as the preferred musical destination and Swarmer as the second candidate**.
