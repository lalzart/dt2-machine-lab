# Automatic cleanup in the BUF experiment

OS 1.16, 2026-10-22. Authorized by “Yes, let’s proceed with buf” after
distinguishing the BUF experiment from existing Flex R5. This is the small
lifecycle integration described in the preceding results, with uninterrupted
implementation authorized. Working artifact:
`scripts/check-buf-auto-retirement.py`, native ColdFire policy and CPU/DSP
transaction with modeled peripherals and original stock voice comparisons.

EVIDENCE: the existing native retirement transaction derives and revalidates
ownership, seals the private descriptor on the DSP and releases through the
original worker. Its caller still explicitly supplies an obsolete token.
The normal packaged Flex R5 builder does not install that adapter.

SELECTED: add an opt-in native policy at the original GUI loop. At most one
candidate is submitted per pass. Scan the eight registry entries in rotating
order, skipping non-live/stale/out-of-range records, the four current logical
BUF roots and all eight frozen roots. Other aliases are checked by the existing
worker validator; the selector grants no permission to free anything. Preserve
the complete existing transaction and DSP seal. Do not modify DSP code.

Only admit when the original recorder getter reports ready (0), no BUF/FREEZE
or stock mutation job is busy, all sixteen kit tracks are ONESHOT, native BUF
setup exists, and no manual diagnostic/FREEZE request is waiting. Native
recorder singleton/getter are authenticated against the stock image. Armed,
recording, intermediate and trim states are excluded. An active transaction is
cancelled if the recorder leaves ready or an explicit FREEZE arrives. A pending
FREEZE serial is deferred, without consumption, while the cancelled automatic
worker still owns the lease; then its original submission runs normally.

Each physical seat has a token-tagged last-attempt audio tick. A failed or
completed automatic transaction sets its last tick again. Retry only after
32768 original audio ticks; this limits retry traffic, never proves ownership.
Unsigned elapsed arithmetic handles tick wrap. New tokens bypass an old seat's
cooldown. Cursor rotation prevents a retained reader on one candidate from
starving other obsolete candidates. Never trigger notes or clear readers in
the policy. Native GUI/worker/ISR continue the protocol without host token,
request, certificate, completion or allocator writes.

State: zeroed explicit emulator scratch at `0x10e00000..0x10e03fff`.
Initialization has cursor/counters/active token/cooldowns zero. No user control
or persistence field is introduced. Reset requires a fresh isolated session.
Epoch changes make old registry entries ineligible. A kit change is revalidated
by the existing transaction. Frozen/current resources are retained. Refusal,
queue failure and timeout retain storage and enter cooldown. Ordinary recorder
starts cancel pending cleanup; original recorder/STOP behavior stays in place.
Playing-sequencer scheduling, other machines, project transition/serialization,
SAVE/readback, physical timing and target placement remain outside this slice.
The stopped sequencer is an explicit test precondition, as in the prior native
transaction experiment; no new transport ownership guarantee is claimed.

No signal algorithm, PCM conversion, gain or interpolation changes. No code is
copied from external products. Existing locally owned emitters and pinned
dependencies are reused unchanged. No new dependency or normal firmware flag.
No merge into Flex R5, installable package, commit, push or hardware action.

## Frozen validation

Seed 0; deterministic short stereo takes; exact bytes. First execute focused
native policy tests: selection/current/frozen/stale/quarantine, bounded scan,
round-robin fairness, queued/in-flight/native recorder states, pending FREEZE,
completion/cancellation, cooldown/tick wrap/seat-token reuse, queue refusal and
register/stack preservation. The falsifying control is a retained candidate:
automatic retries must never substitute elapsed time for DSP permission.

Then run one bounded four-record panel scenario: freeze A, play B, replace with
C, observe retained-reader timeout without freeing B; play C normally and
observe automatic recovery; replace with D and play D; check automatic cleanup,
current/frozen retention and independent stock-file voice renders. If the
retained-reader scenario needs additional ordinary pad events, record them
explicitly; no pointer or descriptor clearing is allowed. Record native
submission/worker/ISR traces and all 32 stock voice comparisons, source hashes,
allocations, candidate PCM/pages and raw streams. No 100-cycle run in this
increment. Exact repeat remains a focused policy test; coupled long-run
qualification is separate. Run full unittest discovery and SINE once on the
final stable sources, plus scoped Ruff and inherited-file checks.

Results: `docs/BUF-AUTO-RETIREMENT-RESULTS.md`. Retain every failed or
interrupted run. A failed focused case is repaired before the panel run; avoid
restarting a long test while still auditing implementation.
