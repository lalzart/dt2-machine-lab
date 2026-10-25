# Recorder retirement diagnostics: pending controls and ownership

Digitakt II OS 1.16, 2026-10-22. Approved scope: the user accepted the proposed
native retirement proof task. Start with observation; freeing and identity reuse
remain disabled. Preserve all existing implementations, shortcuts and dependencies.

## Working definition and selected architecture

The artifact is an isolated native SHARC diagnostic overlay plus executable
`check-recorder-retirement-gate.py` reports. EVIDENCE level: guest target
instructions and exact stock voice PCM in the emulator, never device timing.
No signal processing changes, normalization, UI or hardware installation.

EVIDENCE: the existing observer can see no B readers in the trigger block and
B readers in the following block. Stock `0x1c2b24` processes control; its sample
lookup `0x1c3f78` resolves slot descriptors at `0x257810`. The parameter cache
at `0x2558dc` retains trigger and sample selection after the preceding rendering
work. Two incoming command banks are at `0x264220` and `0x265220`.

SELECTED: observe original control entry, original slot lookup, and post-block
completion. Keep a request-revision-specific union of descriptors known to
reference the requested allocation. Scan cached/incoming selections against that
union, so clearing a descriptor does not hide a still-cached selection. Pending
selection masks are conservative references, even without a trigger bit; no
claim that every selected slot is an audible queued event. Expose trigger bits
separately. Scan all 1,025 descriptors and all 32 voice lanes using the inherited
observer; distinguish logical, private, snapshot, preview and other descriptors.

An observed clear DSP state requires a native control entry and subsequent
post-block completion for this exact request revision, no active/retained lane
pointer, no descriptor overlap, no cached/incoming reference, no unknown extent,
and no serial exhaustion. A direct diagnostic observer call cannot fabricate
that completion. A changed request invalidates the result before publication.
Observation fields are committed with revision last. Consumers must match that
revision and tuple to the current request; an older committed observation is not
valid after a new LP0 request. The per-request alias cohort cannot reconstruct
alias history removed before the request, and it is not an admission seal.

**UNRESOLVED:** this does not close ColdFire cache aliases, patterns/banks,
sample locks, undo/clipboard, CPU preview, save jobs, in-flight control producers,
DMA/cache completion, project transitions, or other playback-machine readers.
These are always explicit unknown ownership bits. `DSP_CLEAR_OBSERVED` is a
local diagnostic result, never `RETIRE_OK`. Permission is always zero. The
existing native echo remains receipt-only; no new status is smuggled into it.
No host readback or fixture assertion may clear these unknown bits.

## State and controls

- No request: counters may run; no valid retirement observation.
- New epoch/generation/sequence/revision: reset alias union and lookup history;
  require a new complete native control pass. Existing observer validates packets.
- Control entry: increment a saturating native serial and latch request revision.
- Slot lookup: count accesses overlapping the allocation before the stock getter;
  execute displaced stock instructions and preserve all live registers/flags.
- Frame completion: observe native entry completion, readers and roots, classify,
  then commit revision last. No state frees, unloads, assigns or changes PCM.
- Duplicate/stale/bad request: inherited validation remains authoritative.
- Frozen snapshot: descriptor remains a permanent root for this increment.
- Project change, panic, rate change, reconnect: no new cleanup handler; unresolved
  ownership remains retained. Protocol epoch tests do not prove real project drain.
- Serial overflow, invalid descriptor, request supersession: fail closed.
- Source PCM, signals, gain and sample interpolation: N/A; observation only.

Constants in the contract generate the compiled header. Code/state use new,
loader-overlap-checked emulator scratch, outside the inherited observer/echo and
Capicola reservations. This is not a hardware reservation. Each diagnostic hook has bounded work: 32 lane checks in the inherited observer,
two 1,025-descriptor scans total per frame, 48 sample selections and 33 bitmap
words per request reset. Total slot-getter hook calls depend on the stock workload;
measure them rather than assume a universal maximum. Record retired instructions,
not physical cycles.

## Frozen experiment

Seed 0, deterministic captured stereo A/B PCM from the authenticated native
queued-worker fixture. Same LP0 pages and wire frames go to an unchanged stock
engine and the overlay. Compare every exercised voice work-buffer byte and
all descriptors/reply bytes (except the separately inherited echo carrier when
composed). Keep source maps, listings, patches, failed controls and reports in
unique ignored directories. Never update inherited expected outputs.

Required literal conditions:
`no-request`, `active-a`, `shared-b-pending`, `native-lookup`, `snapshot-root`,
`late-frozen-trigger`, `descriptor-clear-negative`, `direct-call-no-fence`,
`clear-dsp-fixture`, `retained-reader`, `preview-alias`, `unknown-root`,
`stale-and-project`, `serial-exhaustion`, `exact-pcm`, `permission-never-granted`.

Falsifying comparators: a zero active mask incorrectly approves the pending B
case; clearing descriptors before consumption destroys the pending B playback;
a rootless DSP ABI fixture still cannot authorize freeing due to unknown CPU/
transport roots. The synthetic fixture tests native classification only, not
real root closure. Preserve frozen A throughout normal replacement comparisons.

Run two exact repeats; native CF sender and inherited acknowledgement fault
coverage; unchanged coupled replacement/FREEZE matrix with explicit panel T1
selection; atomic publication; all unit tests; stock SINE replay. Source and
patch fingerprints must remain stable during validation. Tests that involve a
synthetic state or modeled capture/LP0 are labeled at those boundaries.

## Next decision

Only after root closure and a generation-specific completion protocol are proven
may a separate increment release one private stock allocation. Identity reuse
requires a separate lifetime proof. Do not raise the eight-generation cap or
manufacture a bounded memory plateau. Native capture, readback/SAVE, real bar
arming, full startup and physical timing remain independent follow-ups.
