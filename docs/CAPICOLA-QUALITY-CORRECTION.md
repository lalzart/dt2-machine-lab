# Capicola adaptive-splice fidelity correction

Status: proposed, 2026-10-17. Work type: source-reimplementation correction.
Target: Digitakt II OS 1.16. This proposal changes no DSP implementation.

## Goal, scope and working definition

Make the installed CAPI implementation a credible smooth-stretch alternative,
starting with independently demonstrated source-fidelity defects. The user
reports choppy audio and nearly identical stock/CAPI sound. Existing routing
and adapted-oracle tests do not establish the requested musical result.

The first deliverable should be a separate experimental quality revision of
CAPI and an all-feature OS package, with the existing package retained for A/B.
"Working" initially means source, host signal and compiled SHARC equivalence
against the real upstream grain reader in defined interior conditions. Hardware
activation, listening improvement and physical timing are separate gates.

In scope: adaptive splice duration, selected-region boundary behavior needed
for longer fades, float32 progress/termination, independent reference tests,
unchanged native controls/lifetimes and a new candidate package. Out of scope:
new UI, stereo CAPI, transient detector, unrelated machines, larger reservations,
new dependencies, hardware flashing, commits and publication. Preserve existing
research, frozen reference algorithms and previous candidate binaries.

## Source authority, dependencies and evidence

EVIDENCE: authoritative Capicola source is Matthew Nielsen / Heavylight
Industries, revision `120b0b843c18bda373d96eb79d49805545f61556`, clean local
checkout. The linked Reddit post credits that repository and locates its A/B
at 1:05. The author's Digitakt integration source and exact parameters remain
unavailable in the inspected post. This proposal cannot promise demo identity.

Primary sources:

- https://www.reddit.com/r/Elektron/comments/1wyg27f/alternative_stretch_for_digitakt_2/
- https://github.com/heavylight-industries/capicola/blob/120b0b843c18bda373d96eb79d49805545f61556/lib/Granule.h
- `machines/capicola/stretch-live-contract/source-equivalence.json` records the
  existing source hashes and intentional finite/Q24/loop deviations.
- `out/runs/capicola-quality-audit-20261017-01/report.json` records actual
  original-Granule comparisons, fixture/source hashes and retained outputs.

Normative closure: upstream Analyzer.h, SparseLine.h, Granule.h and their
DeluxeLine.h dependency; standard C++ headers. Preserve AGPL-3.0 attribution,
NOTICE and LICENSE. Existing Clang host toolchain, pinned Selache and DigiKit
remain unchanged; authenticate them with `labctl doctor` and run manifests.
Source/header hashes will be bound again in the implementation-ready bundle.
No public firmware redistribution is part of this correction.

## Confirmed mismatch and hypothesis

EVIDENCE: the current finite core, split/capacity derivatives, and STRETCH
reader clamp adaptive splice length to 48..960 source samples. Their references
copy this clamp. At 48 kHz, 960 is 20 ms at pitch 1 and 10 ms at pitch 2.

EVIDENCE: upstream Granule derives an adaptive duration from the span of 128
keyframes, caps it to 90% of available runway, then enforces a 48-sample floor.
Its separately configured fixed fade does not cap this adaptive duration.
The 960-sample fixed-fade value also became an adaptive ceiling in our
adaptation, although upstream treats those as different policies. This was an intentional prototype policy, not an upstream
algorithm requirement, and has never passed a musical-quality acceptance gate.

EVIDENCE: a diagnostic uses the actual unmodified original Granule header and
compares our current finite reader over the interior of twelve-second,
deterministic, int16-quantized mono signals. All nine cases have matching key
counts and no original fixed-boundary rescue events. Prior to the first splice,
maximum PCM error is at most 1.35e-7. In the six cases that splice:

| Signal | First original adaptive span | Current port span |
| --- | ---: | ---: |
| 55 Hz tone | 1163.6 ms | 20 ms |
| 220 Hz tone | 290.9 ms | 20 ms |
| 110 Hz three-note chord | about 430 ms | 20 ms |

The two pitch settings are 1 and 2, timing advance 0.425, leash 128. Times in
this table are source span; output fade duration also divides by pitch.
Repeated splice starts match in these interior fixtures, but the mix weights
and resulting PCM differ substantially. Matching our old oracle therefore
could not reveal the mismatch.

HYPOTHESIS: compressing these content-adaptive transitions into 10–20 ms can
produce the abrupt, grain-like sound the user reports. The measured mismatch
is real; causation for their exact device recording remains unconfirmed.
EVIDENCE: extracted demo frames at 60/66/70 seconds show four bars and, at
70 seconds, tempo 150.0; the original-stretch caption is visible at 66/70.
The demo mixes drums, melodic and bass loops. These observations do not
establish the hidden sample lengths, implementation or audio equivalence.

UNRESOLVED: installed package identity, sample/format, settings and active
backend for both passes. Retain the stock-fallback/trigger-latch check as an
independent branch of this investigation.

## Proposed behavior and fidelity boundary

Preserve extrema analysis, sparse Hermite reconstruction, Q24 source positions,
leash 128, pitch/time separation, smoothstep weights, gain, voices, controls,
project state and preparation ownership. Change the adaptive duration policy
in an explicit quality profile. The old image/profile remains reproducible.

For an interior splice, use the exact local keyframe-span formula from upstream
and the original operation order. Do not cap it at the fixed-fade setting.
For a finite/trimmed/reversed region, derive runway in traversal coordinates
from the selected end and actual cursor, and limit duration to safe available
audio. A finite sample has no moving writer: preserve this intentional
adaptation, and do not claim the original live boundary guards are equivalent.
Loops require an explicit bound and tests across short or silent regions;
copying the original live-ring guard is not acceptable.

Phase uses `smooth(p)=p*p*(3-2*p)`, incoming starts at ideal, both audio heads
advance at pitch, and ideal advances at timing rate. Longer fades must always
terminate at all supported pitch settings (1/32..32): float32 increments near
phase 1 can round away. Use a bounded completion rule and test it rather than
merely deleting the clamp. Reject nonfinite/invalid input, preserve generation
invalidation, and do not allocate or analyze in the renderer. Existing 8 MiB,
16-bank, 32-lane, mono twelve-second and stock-fallback limits remain.

Reuse existing native controls exhaustively: trigger-latched CAPI request,
TUNE, BARS, PLAY, trim and authoritative backend feedback. No controller or UI
layout is replaced. Fingerprint those existing artifacts in the bundle and
require byte-identical CPU transport and stock OFF behavior.

## Frozen experiment before implementation

Source comparison: the actual original Granule header, not our reimplemented
oracle. Interior condition: twelve-second sources, start at source sample
96000, render 144000 samples at 48 kHz, block size 32, leash 128; pitch
0.5/1/2 and advance 0.425. Signals: 55 Hz, 220 Hz, and three sine components
110/138.5913155/164.8137788 Hz, int16 quantization, deterministic seed 1.
No original fixed-boundary guard may fire in an interior equivalence case.
Compare key counts/times, splice onsets/durations and PCM; max error <=1e-4,
RMS <=1e-5 for the corrected interior implementation. The current capped reader
must fail at least one splice-duration/PCM check as a causal negative control.

Additional host matrix: pitch 1/32, 0.5, 1, 2, 32; advance 1/65536, 0.425,
1, 16, 64; all four PLAY modes, trimmed/short/silent regions and loop wraps.
Test long-fade completion, near/end-of-source safety, finite duration, reset,
retrigger, live rate/trim changes, stop, invalidation, independent readers,
NaN/Inf rejection and 1/7/32/127 block partitions. Preserve old-profile bytes.
Bound CPU work and memory; do not label instruction counts physical cycles.

State contract: initialization/reset/panic stop both readers and clear pending
fade; retrigger starts the chosen backend with fresh cursors; pitch/rate update
preserves phase; trim/mode transitions retain the existing live crossfade;
source generation or project replacement invalidates the affected reader;
recall uses existing storage. Freeze/capture and disconnect/reconnect introduce
no new operations and are N/A to this DSP revision. Nonfinite controls fail
closed through the existing validation path. Bytes of diagnostics are not a
musical-state equality contract.

Objective outputs: report.json, old-port.wav, original-granule.wav,
quality-candidate.wav and exact source/artifact manifests in fresh ignored
runs. Use equal gain, no per-clip normalization or alignment fitting. Record
finite/peak/DC, short-window energy and splice discontinuities as measurements,
not a universal smoothness score. Listen to equal-level longer musical samples
and a blind A/B after objective safety; keep the user's actual sample/settings
as the final reproduction gate. A CPU label alone is not listening proof.

Target checks after host gates: compile the quality core, compare actual SHARC
renderer output to the independent reference, OFF equals stock, causal muted
CAPI silence, control/trigger/live-transition checks, sixteen mixed tracks,
startup/packaging, 226+ source regressions and SINE replay. Freeze sources before
long tests. Preserve every failed run and its tolerances. Stop if boundaries,
phase progress, target PCM, reservations or musical A/B regress.

## Decision gate and remaining work

Recommended change: restore content-adaptive fade duration with explicit
finite/loop boundaries and bounded float32 progress, in a separate candidate.
Do not describe it as fixed on the device until the actual A/B is reproduced.

The DSP skill requires a completed proposal and approved implementation-ready
bundle before algorithm edits. This proposal is now concrete and reviewable;
the next gate is approval of this bounded correction, then readiness validation.
No DSP source, firmware bytes, dependency pins or hardware have changed in this
investigation. The diagnostic only builds existing code and the original source.
