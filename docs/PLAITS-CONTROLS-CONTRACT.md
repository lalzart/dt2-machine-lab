# Plaits macro controls: approved implementation contract

Status: proposed, implementation authorized by “Let's go ahead and do that next task.”
Source-reimplementation lane, 2026-10-05. Use the existing lab-native source
lock, control map, run reports and result note; no investigation framework.

## Goal, authority and artifacts

Make the six existing models controllable through dedicated HARM/TIMB/MORP
parameters, starting with WS. Working artifact: plaits-controls.wav and
report.json containing real CPU panel/lock capture plus executed SHARC voice
PCM. User authorization includes routine patch, adapter and test choices.
No new engines, dependency updates, commits, push, flash, continuous sequencer
repair, full-speed emulator, project reload or final-mixer claim in this slice.

EVIDENCE: the six-model source port and exact upstream MIT license closure are
in machines/plaits-bank/source-lock.json. Preserve all existing engine files,
constants, lookup tables, 48 kHz/12-sample processing, float32 update order and
notices. Bind their hashes in the new source-lock.json before DSP edits.
Allowed changes: CPU parameter metadata and the firmware control adapter.
The previous bank, trio and VA remain available as exact reference builds.

## Architecture and control authority

Authoritative controls.json generates controls.h and CPU definitions. HARM,
TIMB and MORP use dedicated parameter IDs 275, 276, 277, fixed mirrors 26, 28,
31 and the existing corresponding frame words. Range 0..32512 (0..127 in
8-fractional-bit display), default 16384; DSP normalization raw/32512 clamped
0..1. MODEL remains discrete 0..5 and latches only on a trigger. Other existing
pitch, length, level and accent semantics stay unchanged. Macro edits update
Params on each 32-source-sample adapter call without resetting the engine;
engine interpolation remains the sole additional DSP smoothing. Existing CPU
smoothing remains unless genuine locked-trigger evidence requires a scoped
correction, recorded with exact patch guards and control timing.

CPU metadata is a sparse extension: three new 60-byte rows, labels and guarded
reader shims in the existing pre-clear flash cave. Original rows and stock
machine descriptors are unchanged. Bound extensions must be paired with
correct sparse addressing; reject unrecognized instruction shapes. Preserve
all registers and flags outside displaced effects. Exhaustively compare old
parameter reads, boundaries and caller state against stock execution. Do not
place required data in the boot-cleared region at/above 0x40312000. New rows
retain SRC owner classification and use plain numeric formatting. Runtime
storage, panel behavior, defaults and locks require actual CPU evidence.

## State, signal and fidelity

Two independent 352-byte lane states at the existing arena; no heap, new
randomness or persistent pointers. Engine union, Params, cursor, age, length,
gain, accent and trigger follow the bank layout. Macro update changes only
Params and later engine evolution. Init/retrigger zeros and initializes the
selected model, replaces the tail, resets cursor and age. Mid-note MODEL edit
does not change the active model. Type switch clears activity; returning without
trigger stays silent. Lane 1 cannot write lane 2 state. Gain remains capped
0.125; existing short attack/fade and 48-to-96 kHz duplication remain exact.
Host/session reconnection uses a fresh checked prepared snapshot; project
persistence and physical-device reconnect are excluded. Freeze, sample-rate
change and variable block partitioning are N/A for this fixed adapter.

## Frozen experiment and acceptance

No stochastic seed: all six MAIN cores are deterministic. Preserve errors and
raw inputs under fresh ignored out/runs directories. Source/input drift must
fail, never update expected baseline automatically.

1. Readiness: dependency doctor, exact proposal/control/source hashes, source
   revisions/cleanliness and all reused license/source files; before DSP edits.
2. CPU: verify sparse reader addressing for all 275 stock IDs and three new
   IDs; invalid IDs retain fallback. Original rows stay byte-identical. Check
   new min/max/default/labels/formatter/mirrors; compare preserved registers.
3. Compiled adapter: each model 120 calls, macros (.25,.5,.75), then (.75,.25,.5)
   at call 40 without trigger, first values again at 80. Two fresh runs exact;
   finite, non-silent, peak <4 before preview conversion. Frozen-macro negative
   must differ for WS. Model changes without trigger preserve active model;
   age remains continuous. Retrigger repeats; lane isolation, type switch and
   silent return. Constant controls match the old bank on identical semantic
   inputs (within 2e-3 for scale quantization, exact for shared endpoints).
4. Actual CPU panel capture: select WS; set all three macro base values using
   encoders, at least eight distinct HARM readbacks; create different macro
   locks on two steps; independently recall locked A/B, unlocked base, A and
   base. Require actual trigger words equal stored readbacks (allow only a
   documented bounded CPU smoothing interval; no synthetic value substitution).
   Capture one sustained macro edit after a real trigger, no second trigger.
   Snapshot and screen capture document labels/readouts; default reset comes
   from a real panel gesture if supported, otherwise label it unresolved.
5. Prepared SHARC replay of those genuine frames: repeated PCM exact; separate
   raw capture from event-isolated/preroll/tail-held adaptation. Locked recall
   audio equal for matching full semantic inputs; wrong/frozen controls and
   disabled hook must differ. Stock-hook parity exact. Keep output level and
   voice-buffer versus final-mix boundary explicit. Provide a repeat command
   that builds, captures, renders and optionally plays the WAV.
6. Eight existing harness tests, Python lint/format, prior bank source/core
   checks as needed, and required SINE replay regression. No broad new suite.

INFERENCE: sparse metadata plus the existing mirror transport should make the
macros usable without changing core DSP. UNRESOLVED until measured: cold boot,
normal PLAY traversal, save/reload, physical timing, runtime arena ownership,
final output and subjective listening quality. Result and gap updates belong
in docs/PLAITS-CONTROLS.md, leaving this frozen proposal unchanged.
