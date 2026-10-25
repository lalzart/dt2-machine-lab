# Native next-bar BUF capture and automatic USE

OS 1.16, 2026-10-22. User authorization: implement native next-bar recording
with automatic USE. Selected first vertical slice: one complete native
16-step cycle, with the existing SAMPLING+YES chord on an initialized selected
BUF. No extra confirmation after completion. Existing Flex R5 and all normal
builders remain separate. No package, device action, commit or publication.

EVIDENCE: the previous performance flow records manually while native notes
play. The old QuickRecord/trigger-comparison models accept injected test bars
and have no capture backend. A new original-code trace observes three native
15 -> 0 master/track-step wraps, pulse 0, with stable pattern master bytes
`001000010800020000ff0000` and repeated native notes:
`out/runs/buf-next-bar-clock-20261022-01/report.json`. The normal source-57
exit is `0x400d8c6e`; the source-44 conditional store remains unsuitable.
Stock controller start/stop, normalization, background loading and BUF
assignment already exist. No signal algorithm or external source is added.

SELECTED: a separate NextBarUI adapter extends PerformanceUI. Intercept only
the authenticated global ARM call into `0x40015f9c` from `0x40016bae` when a
selected BUF is eligible. NORMAL and other ARM callers retain original bytes.
Latch selected track/BUF, recorder controller, project epoch, kit, settings
pool and all 36 recorder-setting bytes. Require initialized BUF, all sixteen
ONESHOT tracks, native PLAY, a primed normal clock, and no mutation lease or
pending FREEZE. This prototype fixes length to ONE BAR; it does not reinterpret
R.LEN/MAX as bars or change stored R.STRT/R.LEN. Stock settings changes cancel
pending/active automatic work. Source and channel remain stock.

The native source-57 exit bridge only observes native fields, validates the
known 16-step normal master, and publishes a monotonically numbered first-step edge and
clock epoch. No host clock/bar/phase writes, synthetic notes, allocations,
recorder calls or publication occur in the interrupt. Discontinuities,
transport changes, pattern changes and unsupported master settings invalidate
the epoch. First PLAY alone is not a new bar receipt. Require a complete 15 -> 0
wrap followed by 0 -> 1: observed grid steps 1/5/9/13 trigger at native
counters 1/5/9/13. The 15 -> 0 wrap alone is one step early. A preparatory
phase audit corrected that candidate before coupled qualification. Duplicate
observations cannot create another receipt.

A native GUI service reserves the existing BUF mutation lease through
arm/capture/publication. At exactly the next numbered wrap it calls original
controller START; at the following wrap it calls original STOP, waits for
native normalization state 4, and submits the existing native BUF copy/load
worker through the stock background service. A separate completion callback
uses the original BUF assignment/rollback primitives and returns the original
controller to ready. No trim view, simulated YES event, host loader or host
completion write. Previous public/frozen takes survive until a full candidate
succeeds. Publication failures do not retry automatically or replace the root.

This is native bar-scheduled service work, not a zero-sample-latency guarantee.
Record boundary tick, actual controller start/stop tick and native CPU delay.
Refuse missed boundaries or service delays over 8,192 native audio-clock ticks;
that threshold is a fail-closed prototype bound, not a device timing budget.
Measure captured PCM against the original modeled recorder input and separately
compare stock playback. Physical DSPI capture start and sample accuracy remain
unverified. The native clock-selector getter must retain the measured result 0 (raw
selector word 1); a preparatory panel diagnostic corrected the initial,
unverified expected value 1. This is a configuration guard, not a general
clock-source classification. External clock,
other scales/lengths, tempo changes and pattern transitions are separate gates.

State: zero-initialized emulator scratch `0x11000000..0x11007fff`. Idle -> armed
-> recording -> normalizing -> publishing -> idle, with result/counters retained.
A repeated chord cancels armed work. STOP/NO, project/kit/settings/selection
changes or invalid clock cancel before publication. Active recording is stopped
and discarded through stock controller actions; normalization already in flight
is allowed to finish before discard. A publishing job receives cancellation
and aborts its candidate in completion rather than freeing an active worker's
memory. No cancellation can borrow a different job's mutation lease. Reset is
fresh session initialization; prior snapshots/current generations are never
invalidated by this state machine. Panic follows STOP cancellation. Native save,
project recall, hardware reconnect and shipping scratch placement are unresolved.

## Frozen experiment and validation

Working artifact: `scripts/check-buf-next-bar.py`; evidence level is executed
ColdFire orchestration/native sequencer plus coupled SHARC stock voice PCM
with modeled capture, LP0, cadence and SEC reset. Seed 0, fresh ignored outputs,
frozen source maps, exact bytes and preserved failures. No 100-cycle stress.

First execute native state tests: full real step cycle, duplicate/no-wrap,
unsupported master/jump/transport reset, next-edge admission, stale context,
second-chord cancellation, stopped/NORMAL/other caller passthrough, late/missed
boundary refusal, normalization readiness, queue/worker/assignment failure,
publishing cancellation and register/stack preservation. Original controller
bodies execute where their ABI matters; native test stubs at worker/queue
boundaries are labeled. Compare deterministic repeats.

Then one fast CPU panel probe: original ONESHOT setup, manual seed take A,
real native pattern and SAMPLING+YES, no further YES/record/trim input until
native automatic assignment. Require one start and one stop from native GUI
code, two consecutive actual wraps, original normalization and queued worker,
exact recorder/page PCM, continuing notes and successful completion. A source-57
notifications-disabled control must never record or publish. STOP-before-bar
must preserve current A and issue no capture. Stop or stale context during
capture must preserve the previous take.

After that probe passes, one coupled two-take flow: seed A, freeze A through
the existing actual chord, arm B at a non-boundary step, let one-bar B complete
and auto-USE while notes continue, then verify stable public slot, frozen A,
nonzero finite active T1 PCM and all 32 voice buffers exact to stock. Independent
stock-file renders of current B/frozen A must match. Capture/LP0 remain modeled;
no final mix, listening, physical timing or hardware claim. Full unittest and
SINE once on frozen native payload/adapter sources; scoped Ruff and inherited
source/dependency audits. Results: `docs/BUF-NEXT-BAR-RESULTS.md`.
