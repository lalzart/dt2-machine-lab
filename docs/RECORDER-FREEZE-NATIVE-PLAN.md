# Native recorder / FREEZE increment: gated plan

Target: Digitakt II OS 1.16. 2026-10-20. User-authorized implementation brief:
`DIGITAKT_II_NEXT_TASK_NATIVE_FREEZE.md`, SHA-256 recorded in
`out/runs/recorder-native-audit-20261020-01/audit.json`.

## Baseline and working definition

EVIDENCE: branch `codex/plaits-macro-controls`, HEAD
`77b1c2a1746a355b66b1a7e1cb61939c9bc0fdb5`, inherited dirty tree and 560
source files. Those sources still match the preceding bounded FREEZE proof.
Existing sources, reports, dependencies and the native 20-second Flex path
remain the regression baseline. Initial status and source copies are retained
in the audit run. `./labctl doctor` passes with the pinned dependencies.

Working means an isolated, reproducible emulator test of actual ColdFire
instructions and original file/loader/UI tasks. Recorder input, sector I/O,
control/audio transport and DSP timing remain named emulator models. No
physical device image or installation is part of this increment.

## Gate A: genuine stock NORMAL first

EVIDENCE: `FlexUI.hook()` currently intercepts trim YES at `0x40022fbe`, and
its installation changes `Y:SAVE` to `Y:USE`. `BufferUI` maps C's first choice
to TAKE and eagerly reserves four visible and eight private slots on opening
the recorder. Label substitution alone cannot establish NORMAL parity.

Implement a separate opt-in adapter; preserve both existing classes. In NORMAL
it must execute original trim/name/save/assign code, leave the stock label and
all other controls intact, and avoid buffer allocation/setup. Reuse the
existing native recorder-peer observer's command/recursive-lock boundary,
rather than replacing original resource/file APIs with host sample callbacks.
Use the same external input and sector models for untouched stock and candidate.

Compare deterministic mono/stereo capture, trim ranges, stock filename edit,
cancel, save failure, assignment and selector changes, MON E, sample pages and
independent stock file reload. Keep original outputs as the oracle. Preserve
failed runs and state exactly when a fixture or model blocks the full flow.
Do not advance into invasive native FREEZE changes unless this gate passes.

Stock entry points to trace: recorder start/stop/discard `0x40015fda`,
`0x400161fe`, `0x40015ff8`; recorder peer `0x400124a0`; chunk wrapper
`0x4001282e`; original trim YES `0x40022fbe`; recorded-file writer
`0x40153994`; sample loader `0x40154540`. C's existing ready/armed dispatch
patch is `0x400209ae`, graphic `0x400221a0`; MON E paths remain original.

## Gate B: native metadata-only snapshot command

Conditional on A PASS. EVIDENCE: stock load resolves at `0x4015b178`, obtains
the key at `0x4015abe6`, finds an existing allocation and associates a new slot.
Cache-hit FREEZE emits invalid/clear then complete slot headers, no PCM pages.
The prior host provider only supplies identity/key/name; full PCM access fails.

Proposed implementation: guarded ColdFire dispatch for a bounded, versioned
metadata table containing epoch, immutable generation key, completed allocation
slot, distinct snapshot identity/slot and fixed name. The diagnostic command
checks committed generation/epoch, name/identity/slot admission, performs stock
association and publishes the completed snapshot only after success. Execute
resolve/key/name and guards as instructions, with no host resource callbacks
for the snapshot. A source cache miss must fail closed.

Do not guess a target code/state reservation: emulator-only mapped scratch is
allowed for this proof and must be described as such. Independently audit all
emitted instructions with the existing ColdFire legality checker and expected-
byte guards. Record actual placement, ABI/register ownership and patch coverage
before execution. A later target reservation is a separate integration gate.

Ownership: BUF n retains its current immutable generation; each frozen sample
retains a distinct logical identity and slot referencing a specific generation.
Keep private generation pins and all prior backing. No reader/lock/queued-event
closure has been established; no compaction, timeout-based reuse or ID recycling.
Preserve Capicola's existing 8 MiB. CPU staging, metadata, DSP extents and durable
files must be accounted separately. No new full PCM snapshot copy.

Failures to test: empty BUF, stale epoch, reused-address trap, occupied/full
slots, identity collision, loader refusal, interrupted header sequence and late
reference update. Failed publication must be unselectable and quarantined;
restore only state whose ownership is proved. Preserve prior playable BUF and
snapshots. Retain project-save/load guards while audio is volatile.

Validation: A→BUF 1→native diagnostic FREEZE→stock selector T6→B→BUF 1;
T1/T5 new triggers use B, T6/active A readers retain A. Compare original SHARC
ONESHOT output with ordinary-file loading and retain the wrong-generation
negative. Count PCM/header pages, guest heap changes, pinned extents and IDs.

## Gate C: gesture decision

Conditional on B PASS. No gesture is approved. Audit original single/double
SAMPLING arbitration, held-state flags and performance contexts. Compare at
most two candidates: SAMPLING held + encoder C push, or a contextual buffer
FREEZE action reachable from SRC without sample-manager navigation. Preserve
FUNC+SAMPLING, SAMPLING+YES/NO, double STOP and project shortcuts.

Present the final implementable choices to the user before binding either.
A native diagnostic command is an acceptable endpoint for B. Feedback should
eventually say `B1-001 FROZEN` without changing page or track assignment.

## Validation and forbidden changes

Run relevant source tests, native CPU legality/patch guards, original stock
comparison, exact DSP references/negative, and `./labctl test sine --replay` on
stable source manifests. Preserve Plaits/Capicola/current Flex source baselines;
do not regenerate expectations. Broaden execution only for changed paths or
unresolved concerns. Document each gate PASS/FAIL/INCONCLUSIVE in
`RECORDER-FREEZE-NATIVE-RESULTS.md`.

Native readback/+Drive Save As for DSP-only audio, quantized quick-record,
reader reclamation and physical timing remain out of scope. No hardware
flashing, uploads, commits, publication, dependency changes or removal of
legacy Flex is authorized.

## Implemented ABI and gate decisions

EVIDENCE: Gate A passed before implementing B. It also exposed a real collision:
stock automatic assignment chose BUF 2's reserved-but-empty slot 301. The new
opt-in `NormalBufferUI` adds an independently audited filter at `0x40016728`
inside the original first-free search. It skips only the checked reservation
list at emulator address `0x10300900`; code is at `0x10300a00`. Empty NORMAL
sessions have only a sentinel and retain the original search. Setup is deferred
until recording to a buffer. No phantom persistent project rows are created.
NORMAL after BUF 1 now chooses slot 304 and preserves BUF 1 at 300.

EVIDENCE: the separate native B implementation uses these emulator addresses:

| Address | ABI / role |
| --- | --- |
| `0x10400000` | Epoch, issued snapshot count, diagnostic fault, volatile flag, busy flag and four current buffer slots |
| `0x10401000` | 32 immutable 64-byte generation records |
| `0x10401800` | Eight 64-byte snapshot records; ready/preparing/tombstone state |
| `0x10402000` | Fixed `/TEMP/Bn-xxx` name strings; no file is created |
| `0x10403000` | Native descriptor lookup: identity, state and epoch checks |
| `0x10403200` | `register(buf, visible_slot, private_pin_slot, epoch)`; no PCM parameter |
| `0x10403800` | `freeze(buf, epoch, expected_live_kit)` → new slot or negative status |
| `0x10405000` onward | Seven native resource thunks at 512-byte spacing |
| `0x10406000` onward | Authenticated displaced stock entry prologues / continuations |
| `0x10407000` onward | Native project-save/load and frozen-slot guards |

A record contains status at +0, lookup identity +4, epoch +8, original immutable
16-byte loader cache key +16, name pointer +32, physical slot/pin +36, and
16-byte logical resource reference +48. Snapshot IDs `0x7ffc0001..8` differ
from the generation keys `0x7ffe0001..32`. Resource resolve requires an exact
four-word reference and returns stock exact status 1. Key returns the original
generation cache key. Native open/read/size reject source PCM access; unowned
file identities execute the original stock prologues and routines.

The command validates epoch, expected kit, current/private cache keys, identity
and slot capacity, derives the project pool through original functions, and
associates a free slot with the original loader. Cache hits retain the original
generation's name, so the command installs the snapshot's inline basename and
name pointer natively before publishing its project reference. No host name
setter is used for snapshots. Failed post-alias operations unload/clear only
the new slot, tombstone the issued identity and quarantine the slot permanently.
Original allocations/private generation pins remain intact.

UNRESOLVED: registration follows the existing **host** BUF commit; this is not
an end-to-end native recorder transaction. The diagnostic caller must pause the
GUI worker and provide IPL 7; the command checks that precondition. Its 32 KiB
mapped scratch is an emulator facility, not an authorized target reservation.
There is no native worker scheduling/deadline, target placement, complete reader
retirement, native DSP readback or project reload implementation.

EVIDENCE for Gate C: `trace-recorder-freeze-gesture.py` traced untouched stock
key events. SAMPLING press is key 50 / flags `0x1`; C push is key 43 /
`0x1` and release `0x10`. After that chord, SAMPLING release has `0x0`, and
the SRC screen remains visible. The ordinary tap action is suppressed by the
stock chord event handling. FUNC+SAMPLING still opens SAMPLES (`0x3` press,
`0x12` release). This is a bounded fixture observation, not all-context proof.

Recommend **hold SAMPLING + press encoder C**, only with BUF n selected and an
eligible performance context. Preserve C push normally and all NORMAL gestures;
debounce one snapshot per press and refuse empty/busy buffers. A future native
UI/worker bridge should enqueue the command and show `B1-001 FROZEN`, rather
than blindly calling the IPL-7 diagnostic from a normal event callback.
Gate C stops for the user's binding choice; this increment installs no chord.
