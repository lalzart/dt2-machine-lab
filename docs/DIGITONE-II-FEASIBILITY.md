# Digitone II machines on Digitakt II: feasibility

Research date: 2026-10-05. Status: research complete; experiment proposed.
Target: Digitakt II OS 1.16 and the existing machine-lab emulator path.
Digitone donor reference: OS 1.11. Public behavior reference: manual OS 1.10D.
The original Digitakt is outside this assessment.

## Assessment

**INFERENCE:** Useful new machines with similar synthesis are realistic with
this lab. Exact Digitone II renderer transplantation is plausible and merits
a small feasibility experiment, but is not yet demonstrated in the requested
direction. A complete, dependable instrument feature involves considerably
more work than generating a waveform.

There are three different deliverables:

1. An independently implemented voice inspired by a Digitone machine.
2. The actual Digitone renderer, privately relocated from supplied firmware,
   adapted to Digitakt state and controls, and compared with its original.
3. A finished Digitakt feature with panel controls, locks, persistence,
   sequencing, mixing and demonstrated physical resource headroom.

Evidence for one deliverable does not complete the others. In particular,
full Digitone polyphony, voice allocation, unison and preset compatibility are
additional projects. One monophonic synth track is a useful initial scope.

## What the local lab already establishes

**EVIDENCE, retained runs inspected:** At machine-lab commit
`c1a0ad675741339c5e154dcb5a58caa7b65b21c2`, the [six-model bank](PLAITS-BANK.md)
contains VA, two-operator FM, analog bass drum, waveshaping, additive and
formant engines compiled into SHARC instructions. Its
[retained report](../out/runs/bank-final-01/report.json) says `passed`, records
exact replay and stock-hook comparisons, and leaves physical CPU/DSP load
unset. This research inspected the report; it did not rerun the audio suite.

The FM port is useful infrastructure, not Digitone FM Tone. The source lock
pins MIT-licensed eurorack to `08460a69a7e1f7a81c5a2abcc7189c9a6b7208d4`.
Its original FM source explicitly uses fourfold oversampling, illustrating why
operator counts alone cannot predict execution cost. See
[the source lock](../machines/plaits-trio/source-lock.json) and
[upstream FM source](https://github.com/pichenettes/eurorack/blob/08460a69a7e1f7a81c5a2abcc7189c9a6b7208d4/plaits/dsp/engine/fm_engine.cc).

The bank report covers selected track-1 voice buffers and real CPU step-preview
control captures. [Integration](INTEGRATION.md) and [status](STATUS.md) still
leave clean startup, live controls, continuous playback, persistence, final
mixer output and physical timing open. Its two lanes are not two independently
allocated polyphonic notes.

The bank has 35,802 code bytes, 12,496 table/data bytes and 704 bytes of lane
state, within an experimentally reserved 466,944-byte loader arena. That is
an existence proof for injecting nontrivial code, not measured free memory.
Runtime arena ownership remains unresolved.

## Relative machine difficulty

The behavior column summarizes Elektron's
[Digitone II manual, Appendix A and B](https://www.elektron.se/wp-content/uploads/2025/10/Digitone-2-User-Manual_ENG_OS1.10D_251022.pdf).
The difficulty and implementation judgments are our engineering inferences,
for a single-voice approximation in the current lab, not measured port costs.

| Machine | Documented core | Approximation difficulty and main work |
| --- | --- | --- |
| Swarmer | Main oscillator plus six detuned oscillators, animation and noise modulation. | Moderate; smallest conceptual design. Reuse oscillator infrastructure, add independent phases, deterministic modulation and normalization. Waveform quality and high-note aliasing still need testing. |
| FM Drum | Three FM operators, pitch sweep, body wavefolding, noise and transient layers. | Medium to high; a reduced percussion voice fits the Digitakt workflow well. Full behavior needs multiple envelopes, routing, retrigger rules and original transient substitutes. |
| FM Tone | Four operators, eight algorithms, feedback, harmonic shaping, two mixed outputs and operator envelopes. | High for a close recreation. Existing two-operator FM reduces toolchain risk but does not supply the missing architecture or exact parameter curves. |
| Wavetone | Two oscillators with waveform interpolation, phase distortion, ring modulation, hard sync and noise. | High for full coverage. Tables and discontinuity handling are substantial work; a reduced version can reuse VA/waveshaping components. |

Swarmer is easiest to describe and implement; that does not establish that it
is cheapest on the DSP or easiest to extract from the donor binary. Conversely,
a difficult algorithm may be easy to transplant if its dependencies are small.

Exact sound matching also depends on gain, interpolation, envelope curves,
modulation smoothing and downstream processing. The manual defines behavior,
not sample-exact implementation. A new engine should use its own identity and
original or appropriately licensed assets.

## Evidence for an actual code transplant

**EVIDENCE, external authors' reported result:**
[The reverse-direction ONESHOT experiment](https://github.com/angellinares/dn2_firmware_explore/blob/b3d4a8751f1250d8fceb3200a1a58b4a8380ed0d/docs/dt2-machine-port.md)
reports moving DTII 1.16's renderer into DNII 1.11, with bit-identical offline
results for four playback modes. Its dependency set was four functions,
611 instructions, two coefficient tables and ten relocation sites. Later
sections describe CPU control adaptation. The implementation was removed from
the public repository on September 29; the research record remains. We did not
independently reproduce it. It is not a DNII-to-DTII demonstration or hardware
validation.

**INFERENCE:** This is strong precedent for a small renderer transplant, not
for swapping complete DSP images. It supports testing a donor engine before
assuming either that a port is trivial or that it requires a rewrite.

The existing [DigiKit comparison](../../Digitect%20firmware%20research%20project/work/digikit/docs/findings/11-sharc-cross-image-comparison.md)
at commit `277760aad51b036a4756db051409d4d3b1eeccbc` records shared DSP stages
alongside product-specific code. Older local DNII 1.10E/DTII 1.15C architecture
work also supports platform lineage, but its addresses must not be reused for
1.11/1.16. Shared helper code does not establish a common voice ABI.

The donor's [voice-path investigation](https://github.com/angellinares/dn2_firmware_explore/blob/b3d4a8751f1250d8fceb3200a1a58b4a8380ed0d/docs/sharc-voice-path.md)
explicitly rejects treating its nearby state address as the DTII voice-record
array. State layout, initialization, tables, indirect calls and global memory
are therefore central port questions.

## Work common to every engine

**UNRESOLVED in this lab:** CPU pages and parameter storage; complete control
transport; live changes and locks; note-on/off, release and machine switching;
multiple tracks; saved project reload; sample-free startup; final filter/AMP/FX
and mixer behavior; safe runtime memory placement; worst-case physical timing.
A synth with many parameters also needs a deliberate page or macro design.

The current source hook produces 64 samples at 96 kHz per call. Plaits uses
12-sample blocks at 48 kHz through an adapter. A Digitone transplant needs its
own measured buffer/rate contract; its nominal output sample rate alone does
not tell us where it can connect.

Neither the SHARC part's maximum clock nor slow host emulation measures spare
hardware capacity. New-engine profiling must separate instruction counts,
actual cycles, memory traffic and existing sampler/effect load. Running one
voice does not establish sixteen voices.

## Recommended next experiment

**HYPOTHESIS:** At least one DNII engine can be isolated as a manageable
renderer plus setup/state/table set, then called from the DTII source hook.
Start by comparing Swarmer and FM Tone dependency boundaries; choose the
smaller measured set. No transplant has been attempted in this research.

1. Pin and hash DNII 1.11 and DTII 1.16 inputs. Obtain one deterministic donor
   voice render using the original engine and retain its exact starting state.
2. Identify the renderer and required setup, all calls and table reads, state
   fields, global accesses, output rate and block size. Record any unresolved
   indirect dependency rather than silently omitting it.
3. Relocate that bounded set into a private candidate; compare the same
   initialized voice and parameter timeline with the original. Require exact
   float PCM for a pure relocation. Test silence, repeated initialization,
   retrigger, release and two independent states.
4. Only after isolated equivalence, connect one DTII track with a small fixed
   parameter set. Reuse existing repeat, stock-isolation and disabled-hook
   controls; retain voice PCM and per-block instruction counts separately.

Suggested artifacts: `donor-reference.f32`, `relocated.f32`, dependency and
relocation manifests, and `report.json` under one new ignored run directory.
A failure to isolate initialization or state is a useful result: it establishes
why an independent approximation is cheaper. This is a proposed research
experiment, not a frozen implementation contract.

If the priority is new playable sounds instead of exact Elektron identity,
start with a Swarmer-inspired voice, or a reduced FM percussion voice for the
strongest fit with Digitakt sequencing. First improve the shared control and
playback path so another engine does not merely add another offline demo.

**Effort judgment:** reduced offline voices are a days-to-weeks class of work
with the present harness; complete controls and dependable integration are a
weeks-to-months class of work. These are planning scales for an experienced
developer, not delivery commitments. Exact-transplant effort cannot be priced
responsibly before the dependency experiment; hardware readiness is unestimated.

## Research scope and provenance

Inspected official manual sections A.2.1–A.2.4 and Appendix B; the pinned local
machine source locks, integration notes and bank report; DigiKit machine and
cross-image findings; and the DN2 research repository at
`b3d4a8751f1250d8fceb3200a1a58b4a8380ed0d` (retrieved 2026-10-05).
Targeted web searches for Digitone machine rendering/transplant work found no
completed DNII-synth-to-DTII port in the inspected sources. This is a bounded
search result. The official support landing page returned HTTP 403; the
versioned official manual was readable, so no latest-release claim is made.

No DSP source, dependencies or firmware were changed. The scope was feasibility
research, so novelty, cultural design and full implementation-contract sections
of the DSP design workflow are inapplicable. Repository instructions requiring
short engineering notes and retiring claim ledgers govern this note.
