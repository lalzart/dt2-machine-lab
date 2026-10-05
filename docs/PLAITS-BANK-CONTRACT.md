# Plaits six-voice bank: frozen implementation contract

Status: proposed and implementation authorized by the user's request to
implement another set of voices. Source-reimplementation lane, 2026-10-05.
This repository-native bundle uses this immutable proposal, source-lock.json,
controls.json, the repeat script and a separate results note. No new governance
framework or hardware release is introduced.

## Scope and working definition

Add waveshaping/wavefolding, harmonic additive and granular formant MAIN engines
as MODEL 3/4/5, retaining VA/FM/analog BD at 0/1/2. Artifact:
`out/runs/<fresh>/plaits-bank.wav`, compiled CPU/DSP overrides and report.json.
Evidence: bounded upstream host equivalence, compiled SHARC execution, real CPU
model-lock transport and prepared voice-buffer PCM. The user authorized this
implementation; routine architecture/source-port choices belong to this task.
No commit, push, flash, dependency update, emulator timing repair, real-time
playground, final mixer, LPG, AUX or complete Plaits catalogue in this slice.

## Authority and license closure

EVIDENCE: the exact pinned eurorack/stmlib revisions and MIT file notices in
source-lock.json authorize this port. The transitive quoted-include closure,
upstream engine sources, resources and reused VA/trio files are individually
hashed. Upstream and dependency checkouts must remain unchanged. Generated
lookup tables retain original literals; integer waveshaping table elements may
be widened to 32-bit without value changes. Required MIT notices stay in every
adapted source. Host oracle executes the complete untouched original engines.

## Signal and state contract

Preserve upstream 48 kHz processing, 12-sample blocks, original 47872.34 Hz
calibration, float32 arithmetic/update ordering, parameter interpolation,
anti-aliasing and table interpolation. MAIN signal graphs:

- WS: bandlimited slope -> interpolated waveshaper -> Hermite wavefolder;
  upstream Tame attenuation and macro curves unchanged. Exclude independent
  triangle/sine/fold_2 AUX and its interpolator.
- ADD: original 24-partial spectrum update/normalization -> two 12-partial
  Chebyshev banks summed to MAIN. Preserve unusual normalized smoothing.
  Exclude independent eight-partial organ AUX. Replace allocator storage with
  fixed 24-amplitude state and two oscillator states (208 bytes).
- GRAIN: two synced grainlet oscillators -> sum -> original one-pole high-pass.
  Preserve the second grainlet, which contributes to MAIN; exclude independent
  Z-oscillator AUX and its filter. Scratch array holds twelve samples.

The reused code defines exact equations; generator extracts source function
bodies with explicit specialization. New state fits a 256-byte tagged union
containing the previous Trio, plus a four-byte model selector: Bank 260 bytes.
Each independent firmware lane adds Params, 12-sample output and the existing
cursor/envelope fields: 352 bytes, two lanes 704 bytes. No heap, pointers inside
persistent new-engine state, randomness, I/O, or shared mutable DSP state.

Init/reset zeros every state word and initializes only the selected model.
Core model selection clamps 0..5. Reset equality means exact PCM for identical
input vectors from initialization; changing model/retrigger resets the voice
and replaces its tail. Other lane state must remain byte-identical. Type switch
clears activity; silent return without trigger. No freeze/reconnect/persistence
semantics added. Engine smoothing runs inside each block. Firmware controls
latch on trigger; mid-note changes preserve existing voice state/output.

Keep existing note/macro/length/level transforms, gain cap 0.125, source 48 kHz
with duplication into 96 kHz work buffers. New models use existing VA/FM short
attack and final fade; BD retains original special treatment. Full engine MAIN
is compared before the wrapper. Control-map authority is controls.json;
generate C constants/model limit. CPU MODEL maximum becomes 1280 (5*256),
retaining track-1/type-7-only smoothing bypass. Labels remain numeric; original
macro UI limitations remain explicit. All firmware patch bytes remain guarded.

## Literal bounded experiment and readiness

Existing try-plaits-trio.py mechanics are reused in a separate bank repeat
script. Before DSP edits, validate source/control/proposal hashes and fixed
capacities into an ignored readiness report. These files define the native
implementation bundle; results and remaining gaps go in docs/PLAITS-BANK.md.

For all six models: host original C++ vs C99 MAIN, 4000 blocks (one second),
settings (48,.25,.3,.4), (60,.7,.8,.2), (36,.9,.1,.8), first setting again,
1000 blocks each; rising triggers on change, accent .8. Check all 16 combinations
of note 0/127 and macros 0/1 for 120 blocks. Max error <=1e-5 and finite samples.
Repeat initialization/render exactly. Independent MAIN oscillator states must
not depend on omitted AUX. No stochastic seed is needed.

Compiled target: two identical 120-block renders/model with the same four
settings at 30-block intervals; MAIN error <=2e-3, finite and exactly repeated
PCM, plus per-block emulator instruction counts. Preserve original trio host
and target PCM on equivalent vectors. Image equality is required for unchanged
trio rebuild, not for differently placed bank code.

Integrated adapter: every model non-silent and repeatable; selector latching,
independent lanes with unequal new models, retrigger, switch-away/silent return;
wrong-model negative and exact old trio PCM on matched controls. Real CPU panel
capture stores and recalls new MODEL 3/4/5 plus old/new return, without synthetic
selector substitution. CPU shim check covers all eight stock types and six
selectors. Firmware replay: exact repeat, correct model sequence, non-silent
new-model intervals, recall equality, stock hook parity, disabled-hook negative.
Mask unrelated track events and identify padding/adaptation explicitly.

Retain failed and passing runs, image/PCM/source hashes, WAV previews and cost
reports under fresh ignored directories. Run existing eight harness tests,
lint/format, deterministic regeneration and SINE replay regression. Source
changes invalidate in-flight freshness checks. Never relax a failed tolerance
or change the expected baseline automatically.

## Gaps and decision rules

UNRESOLVED: sustained target numeric drift outside the short vector, worst-case
cost, physical cycles/load, live sequencing, macro display fidelity, project
reload, clean startup, runtime arena ownership and final mix. Passing source or
voice PCM does not close these. If source parity fails, diagnose translation;
if compiled parity fails, diagnose compiler/ABI without silently changing DSP.
INFERENCE: these deterministic fixed-state engines are a reasonable next batch;
resource measurements and numerical checks must establish the actual result.
