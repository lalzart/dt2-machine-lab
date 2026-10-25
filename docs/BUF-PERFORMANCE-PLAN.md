# BUF during native pattern playback

OS 1.16, 2026-10-22. User authorization: “Let’s continue the performance
workflow we’re building towards.” Selected uninterrupted increment: original
record/trim/USE replacement, automatic retirement and an actual native FREEZE
gesture while a native pattern plays. Existing Flex R5 remains separate.

EVIDENCE: the previous BUF cleanup passed only a stopped-sequencer panel run.
The earlier quick-record trials are dry request comparisons. The source-44
conditional store is not the normal bar clock. A new read-only source-57 trace
shows native master-step/track counters progressing and repeated track triggers.
Original getter `0x400d6726` returns the OR of native active/mode fields; the
trace observes both 1 during PLAY and both 0 after STOP. Probe:
`out/runs/buf-performance-clock-20261022-01/report.json`. Peripherals/cadence
remain modeled; no musical edge is supplied by the host.

SELECTED: a separate native input bridge on the authenticated original global
key handler. SAMPLING held plus encoder C push (keys 50 + 43) requests queued
FREEZE of the selected track's logical BUF. Resolve the track through original
ProjectSettings getters and its live kit sample slot, then match the four
native BUF roots. Do not use the remembered recorder destination as a proxy.
Require native PLAY state 1, recorder ready 0, the existing initialized BUF
context, all sixteen ONESHOT tracks, no pending FREEZE and no conflicting stock
mutation. An automatic retirement lease may yield to the new explicit request.
FUNC, YES, NO and transport modifiers refuse interception. Non-BUF tracks and
all unrelated keys remain stock. A recognized chord consumes C edges and its
SAMPLING release; ordinary SAMPLING navigation gains no delay. Encoder rotation
is untouched. A native latched destination feeds the existing queued FREEZE
submitter; epoch/kit drift refuses before submission. No host request writes.
No assignment, PCM copy, DSP allocation or file is created by the input bridge.
The queued worker creates the immutable alias as before.

State: zeroed explicit emulator scratch at `0x10f00000..0x10f03fff` holds target,
epoch, kit, chord ownership and diagnostic counts. No saved settings or new
display page. Recognized chord ownership lasts through release; duplicate C
presses cannot queue twice. Reset requires a fresh session. STOP prevents a new
request; existing worker epoch/lease checks retain their prior behavior. New
project/kit state rejects a queued stale target. Armed/recording/trim contexts
preserve original actions. Current and frozen generations remain pinned.

No signal algorithm changes, external code/assets, dependency updates, normal
firmware builder changes or Flex R5 merge. Reuse the existing locally owned
native key bridge and queued FREEZE/cleanup transaction. The new reserved region
is emulator scratch, not a hardware reservation. No package, commit, push,
publication or device action. All playback evidence is raw voice PCM, distinct
from DAC/listening/physical deadlines.

## Frozen checks

Working artifact: `scripts/check-buf-performance.py`. First focused ColdFire
controls: all four selected BUF roots, unrelated slots, stopped transport,
recorder states, machine/busy/modifier contexts, auto-lease priority, single
request per chord, release consumption, exact ordinary-key pass-through and
stale epoch/kit. Execute original transport getter with prepared native fields.
Check registers/stack and deterministic input replay.

Then one bounded coupled panel sequence: record A; program an ordinary 16-step
pattern with native panel events and start PLAY; verify native transport fields,
step progress and repeated control-frame triggers; perform actual C chord and
keep frozen A; record B/C/D while PLAY remains true; let the pattern's own trigs
advance old readers and permit automatic cleanup, without manual drain pads;
check current/frozen stock-file playback; STOP/restart/STOP and observe native
state and renewed trigs. Assert no input/host writes to FREEZE or retirement
command state, no synthetic notes/bar ticks, unchanged assignments across
FREEZE, all 32 voice buffers exact to original stock execution and unchanged DSP.
Native pattern progression is required in every recording interval. Refusal or
retained readers cannot be bypassed to make the scenario pass.

Seed 0, deterministic short stereo input, exact bytes, fresh ignored output,
retain failures and frozen sources. Full unittest and SINE once on stable
sources; scoped Ruff and original-file/dependency checks. No 100-cycle run.

UNRESOLVED: native next-bar capture/length completion/automatic USE, variable
length/scale/external-clock bar semantics, other playback engines, arbitrary
project transitions, native BUF readback/SAVE, final output, target placement,
device timing and interactive device feedback. The performance chord's outcome
is observable in the native snapshot slot/name, with no new success overlay.
Results: `docs/BUF-PERFORMANCE-RESULTS.md`.
