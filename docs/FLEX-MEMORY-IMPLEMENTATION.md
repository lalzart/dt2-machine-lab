# Flex memory implementation contract — 2026-10-08

Status: bounded optional source-ownership stage implemented; broader capacity and
lifecycle redesign incomplete. See [results and exact limits](FLEX-MEMORY-IMPLEMENTATION-RESULTS.md).

Authority: user approval relayed from Octatrack Memory Architecture task
01a11942-7e84-7703-9835-54a0143df328: accounting, transactional failure cleanup,
then verified save-backed source reclamation. This supersedes the research-only
boundary in FLEX-MEMORY-REDESIGN-2026-10-08.md. No additional experiment approval
is required. Native CPU work only; no new DSP algorithm or audio normalization.

This is the repository-native implementation contract for the DSP research skill.
The report defines state/controls/budgets; source manifest and observed starting
state are in out/research/flex-memory-implementation-2026-10-08.

Working artifact: optional native OS 1.16 ownership overlay plus reproducible
CPU/resource/stock-loader tests. Target build and emulator source/PCM evidence
are acceptance layers, not physical timing or hardware readiness.

Preserve: immutable 20-second mono/stereo takes; old patterns; ONESHOT assignment;
named save; project persistence; Plaits/menu and unrelated Capicola work.
Forbidden: speculative free, destructive buffer reuse, hidden-file acceptance,
current-track-only garbage collection, assumed CPU heap capacity, commits or
hardware upload. New global memory reservations require verified ownership.

Implementation sequence:
1. Freeze original sources, trace actual loader instructions and source reads.
2. Register a completion invariant and negative early-release/delayed-reader test.
3. Add bounded accounting and safe source management only where proof holds.
4. Add transactional candidate cleanup, stable identities/epoch checks, dialog and
   resource pins; never recycle externally visible IDs under old handles.
5. Save-backed handover routes future opens to verified durable data and drains
   existing source users before reclaim. Playback memory remains stock-owned.

Literal trace conditions: mono/stereo at 141,1025,960000 frames, deterministic
PCM formula based on frame index; two-slot alias, replacement and premature
source poisoning negative. Event order is CPU instruction order, not wall time.
No renderer/smoothing change. PCM equality is byte-exact; source retirement
requires zero reachable or in-flight RAM borrowers; failure preserves old refs.

State operations: initialization starts fresh ownership state; pattern recall
retains project roots; stop/panic does not free takes; capture freezes its source;
save pins its immutable input; failed save leaves it intact; project transition
invalidates pending commit tokens and drains borrowers; reset/reboot loses only
unsaved volatile state. Unknown teardown boundaries pin rather than reclaim.

Physical controls remain YES/USE and idle recorder FUNC+RECORD named save.
Any diagnostic gesture must be scoped to idle recorder and tested for stock
fallback. Control mapping is exhaustively tested rather than generated.

Validation: native instruction/ABI checks, actual stock-loader PCM traces,
resource stale-handle/read/cancel tests, save aliases and project roundtrip,
repeated-use plateau, failure injection and source/byte guards. Full unit suite
required after harness edits; SINE replay if DSP/adapter behavior changes.
Retain successes and failures in unique ignored out/runs directories.

Dependencies: existing pinned DigiKit and private OS 1.16 fixture only. No source
port from Octakit; no dependency installation or update. No license expansion.
If safe handover cannot be established, document the exact retained pin and
remaining stage instead of asserting completion. Significant unavoidable
capacity changes require a concrete user decision; the provisional 16 MiB
research budget is not a firmware default.
