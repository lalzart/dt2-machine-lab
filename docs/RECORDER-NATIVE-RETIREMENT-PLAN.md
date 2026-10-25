# Native buffer retirement transaction

Digitakt II OS 1.16. Authorized by the user's “Okay yeah let’s proceed” after
the native-retirement recommendation, 2026-10-22. Implementation may proceed
through validation without another approval. Working artifact:
`scripts/check-recorder-native-retirement.py`, at the native-instruction,
modeled-peripheral and voice-PCM evidence layers.

## Selected architecture

EVIDENCE: the eight-seat experiment completes 100 replacements but still uses a
paused-test certificate and host delivery of a real DSP diagnostic. The existing
native CPU ISR / SHARC SEC request/reply carrier transports diagnostic receipts.
Neither establishes a running retirement transaction.

SELECTED: add an isolated native CPU lease and two jobs on the original worker
service: prepare and commit. A test command supplies only a request serial and
generation token. Native code derives epoch, kit, registry entry, private slot,
exact allocation extent and ownership. It refuses current/frozen/aliased takes,
in-flight sample mutations, unsupported machine contexts and stale projects.
The first running test uses the stopped sequencer and ONESHOT, with eight
reserved private slots, four stable public buffers and immutable FREEZE aliases.

During the lease, metadata acquisition of that token fails, foreign stock sample
load/unload/clear operations fail, and native recorder/FREEZE admission is busy.
Mutation authority also requires the native active-unload flag, set only around
the final stock unload call. A matching shared worker task or queued commit
phase alone grants no authority to another background job.
The stock in-flight operation counter is acquired before this permission check
and held through the original body. An entry preempted before acquiring the
counter must recheck the live lease after acquisition; the existing FREEZE gate
continues to run inside the same counted interval.
An independently guarded original DSPI2 driver rejects outgoing control frames
that select any reserved private slot, including after physical-slot reuse.
These private slots are internal ownership pins, never track destinations.
Both authenticated original driver callers are covered at the driver entry.
Unknown transfers invalidate a pending retirement. Ordinary allowed frames and
their original driver/callback path are preserved.

The native CPU sends the existing ordered LP0 request after ownership admission.
The unchanged native DSP observer/gate must see a fresh control pass, no active
or retained ONESHOT reader, no queued/cached selection, no logical/snapshot/
preview/other descriptor, one exact private owner and no unknown extent. A new
scoped DSP function clears only that private descriptor after these checks,
closing later descriptor-based acquisition before publishing completion. It
never clears voice pointers or frees PCM. A fixed eight-entry sealed-tuple table
supports retry after a lost completion without treating an empty descriptor as
proof. The original general diagnostic permission stays zero and unknown bits
stay 127; this protocol is restricted to the guarded private namespace.

Completion is a 64-fragment message carrying epoch, unique generation token,
sequence and a distinct RTOK domain word through the previously audited padding
byte. The request's extent remains bound to its immutable sequence. Native ISR
matching requires the entire ordered message; a receipt echo cannot satisfy it.
Once confirmed, a GUI poll queues commit on the original worker. Commit checks
the live task lease, epoch/kit, exact CPU key/extent, snapshot roots and aliases
again, atomically tombstones the token, then calls the original stock unload
and native dead-node cleanup. Only a short final state change masks interrupts;
the stock unload does not run at IPL 7.

Timeout, cancellation, stale/partial/corrupt replies and refused ownership retain
the CPU allocation and token. A DSP-only descriptor seal can survive a lost
reply; retry requires its exact native sealed tuple. New tokens never wrap.
No host writes a certificate, diagnostic result, registry commit or completion.
No host direct-call retirement or diagnostic driver pump is allowed.

## State and controls

Initialization: empty transaction, no lease and no completed request. Request
serial plus token are test command inputs, not a performance shortcut. Prepare
and commit use the original background task; callbacks run on the GUI task.
Only one transaction may be outstanding. Busy input cannot replace its context.
Pending failure releases admission while retaining allocation ownership. Reset
requires a fresh isolated session. Project changes refuse; no project migration
or persistence is introduced. STOP remains stock. No new Panic, sample-rate,
mode-recall or reconnect operation is introduced. FREEZE pins remain immutable.
PCM, gain, interpolation and stock synthesis are unchanged; signal processing
equations and gain normalization are N/A because this is lifecycle control.

## Frozen experiment and decision rights

Seed 0, deterministic stereo captures; exact comparisons, no numeric tolerance.
First prove three native recordings, one extent reuse and a frozen snapshot.
Exercise active and inactive retained readers, pending selections, foreign and
in-flight mutations, sealed-token lookup, forbidden private controls, frozen/
current roots, cancellation, wrong epoch/kit, stale sequence, disabled SEC,
delayed/dropped/duplicate/reordered/corrupt/stale/zero replies, timeout and retry.
The false comparator is the earlier receipt or zero-reader observation: neither
may release memory. In an explicit destructive fixture, clearing a pending
descriptor loses playback; the implementation must refuse that state.

Then run 100 native record/trim/USE replacements with one frozen take retained,
releasing obsolete generations through native jobs and native return transport.
Repeat exactly. Compare all 32 voice buffers against original stock execution
with the same native publication/control history, plus stock-file oracle
milestones. Require distinct tokens/PCM, stable public selection, bounded source
metadata and DSP storage, and stale-token failure after entry/address reuse.
Save source manifests, code/listings, request/reply streams, job/ISR traces,
allocator states and failed controls in fresh ignored run directories. Run
focused native tests, the complete unit suite and SINE at the stable milestone.

Normal firmware builders, inherited sources/expectations, dependencies and
hardware remain unchanged. This is an original lifecycle protocol around owned
local fixtures, with no copied third-party DSP algorithm or firmware release.
Use the existing isolated conditional-MODIFY runtime and audited compiler paths.

UNRESOLVED: arbitrary projects and all playback machines, external producer
coverage outside this restricted namespace, actual DMA/cache coherency, full
RTOS startup, physical deadlines, native readback/SAVE, code/state reservation
and device operation. LP0 delivery, capture production, event cadence and SEC
reset fixtures remain explicit emulator models. Passing this contract must not
be promoted into a general hardware retirement guarantee.
