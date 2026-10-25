# Reader lifetime and queued FREEZE increment

Target: Digitakt II OS 1.16; isolated emulator experiment. Implementation
contract, 2026-10-21:

1. Preserve the current eight-generation admission cap. No native backing or
   identity reuse without a DSP acknowledgement covering active readers,
   queued triggers, logical roots and frozen snapshots. A host scan of SHARC
   memory cannot authorize native reclamation.
2. Test the stock unload/reuse boundary with an active original ONESHOT voice.
   Record the failure of premature reuse against an unchanged stock oracle.
3. Queue FREEZE through the original background service (`0x400f0ab8`), using
   native small-function copy/destroy and completion callbacks. The original
   IPL-7 diagnostic entry remains intact. The new body requires the job owner,
   current RTOS task, running phase and a private execution lease.
4. Share admission with the recorder worker. Refuse colliding jobs, check the
   stock loader busy flag, and block other tasks from entering load/unload/clear
   during the FREEZE job. Keep interrupts enabled; never infer synchronization
   from a host pause. Recheck epoch and kit in the worker before publication.
5. Use a test command mailbox polled by the native GUI loop. Host writes only
   a request serial; destination/context latching, queuing, mutation and
   completion execute in firmware instructions. No performance shortcut is
   connected in this increment.
6. Prove replacement, old snapshots, rollback, empty/full/stale requests,
   duplicate requests and serialization. Repeated capacity refusals must not
   allocate sample backing or consume identities.
   If native retirement remains blocked, do not manufacture a successful
   hundreds-generation plateau using host reader counts.

All code/state placement is explicit emulator scratch. Normal builds, legacy
Flex, Plaits, Capicola, dependencies and shortcut prototypes are preserved.
Native SAVE/readback, full project-root closure, coupled real-time timing and
hardware installation remain separate gates. Results and reproduction follow
after executable validation.

## Native retirement gate

The CPU allocation record (`0x405a0f64`, stride `0x34`) owns a tree of sample
slot/cache aliases. `0x401540c6` removes the requested slot from that tree,
decrements `record+0x30`, and returns/merges the allocation when the last such
alias disappears. It then clears the slot and sends a stock update. This is
not a SHARC voice count. Its inspected instruction path contains no
generation-specific DSP retirement acknowledgement.

The DSP slot descriptor (`0x257810 + slot*0x14`) and the installed voice
pointer (`0x2412cc + lane*0x1d8`) have distinct lifetimes. A cleared descriptor
prevents a future trigger from obtaining that descriptor; it does not itself
establish that old voices have stopped reading the former allocation. An
empty slot, stopped sequencer, changed track selection, or CPU source-reader
count is insufficient. The original allocator can only be used to reclaim
backing after the independent DSP-reader gate has been satisfied.

The known return halfword at DSP `0x266220/0x267220 + 0x1a`, CPU
`0x800048a6`, is already used by Capicola feedback. It is not free space for
an invented acknowledgement. No new reply field, LP0 tag, direct pointer
access or Capicola reservation is appropriated in this experiment.

An incremental native protocol would need:

- Immutable generation and project epoch in each retirement request, plus a
  monotonic transport sequence/barrier. First stop admitting future references
  to that generation; committed buffers and frozen snapshots remain roots.
- A DSP acknowledgement after all earlier control events have been consumed
  and all relevant old readers have finished. For ONESHOT, audit all 32 lanes
  and the final read/block completion; other machines may retain additional
  reader state. A host scan is only an oracle for that acknowledgement.
- A CPU check that the acknowledgement matches the outstanding generation,
  epoch and sequence, with no cache aliases, snapshots or unresolved project,
  queued-trigger, sample-lock or save-job roots. Then release the private stock
  slot; retain identity tombstones until a separate handle-lifetime proof permits
  reuse. A backing allocation and an identity are not the same resource.
- Lost, duplicate, stale or reordered replies must retain memory and refuse
  further capture at the bound. Project transitions require their own drain
  barrier. SAVE also needs a readback lease and still has no native PCM path.

This is the next implementation gate, not an implemented protocol. Raising
the generation limit or scanning DSP memory from Python would conceal it.

## Queued FREEZE architecture

The new opt-in adapter adds native scratch `0x10700000..0x10703fff` (16 KiB
mapped, not a hardware reservation). A request serial is consumed by a small
poll at the original GUI loop `0x40033d00`. The original displaced `PEA` and
continuation are retained. No request means no native job or navigation.

The GUI latches the existing C DEST, project epoch and current kit. It admits
one job using the recorder worker's busy word, constructs two stock-compatible
small `std::function` objects, and calls the original service singleton
`0x40198a16` and enqueue operation `0x400f0ab8`. Their native copy/destroy
manager carries a pointer to fixed job state and allocates no capture PCM.
The original service owns its ordinary queue storage.

Native wrappers around load, unload and clear count in-flight operations,
including nested calls, from entry through return. Admission and worker entry
both require that count to be zero. Updates briefly mask interrupts for the
register/count update and restore the prior SR; the loader and FREEZE body do
not run under that mask. Once the job owns admission, new sample mutations
from other tasks are refused. This also covers a sample operation that was
already entered and then paused by a task switch before FREEZE admission.
The wrappers preserve stack argument order and the stock return value.

The worker checks the stock loader-busy flag, then sets a private execution
lease and records the current RTOS TCB. The authenticated OS 1.16 scheduler
loads that TCB from `0x47db3f64` at `0x40000418`. The FREEZE body requires the
lease, running phase, common admission owner, exact TCB, epoch and kit; it
rechecks that gate before final publication. Its stock cache-hit aliasing,
native name/reference creation, quarantine and rollback remain the existing
FREEZE algorithm. No source OPEN fallback or PCM readback is introduced.

Completion receives the original integer result on the GUI thread, records
it, and releases admission. The old public FREEZE command keeps its IPL-7
diagnostic contract; its default payload is required to remain byte-exact.
The queued adapter deliberately rejects the former host `.freeze()` method.

The mailbox is a test command input, not a performance shortcut. The harness
writes only a request serial and wakes the ordinary blocked GUI with a zero
encoder event. DEST/context latching, admission, scheduling, aliasing and
completion execute as ColdFire instructions. Peripheral timing, page delivery,
recorder PCM and prepared SHARC replay remain the existing explicit models.

## Reader negative control

`scripts/check-recorder-reader-lifetime.py` uses actual original CPU file
loading, unloading and allocation, followed by original SHARC LP0 and ONESHOT
execution. Its deliberate premature-reuse control is confined to that probe.
It does not change the native BUF policy.

Two deterministic, two-second stereo ordinary files use the same allocator
span after A's last CPU alias is unloaded. Both DSP descriptors are
`[32, 192544, 192000, 48000, 1]`. A's installed voice pointer is
`0x8422b9e8`. The unload produces one empty LP0 header. Applying it leaves the
voice active, and the next eight voice blocks remain exact against retained
A. Publishing B at the reused address changes the old active reader's next
sixteen blocks. The unchanged A oracle and unsafe output have distinct hashes:

| Voice result | SHA-256 |
| --- | --- |
| Retained A, safe oracle | `6987194aee61e13e6dc2611c7b90b0f2ca6683d64aa8ec6d57eb53ef728ee2de` |
| Old reader after deliberate reuse | `4d794aff720c5d6a68d7a0b59d5240cfecad79a466d34b3036faa4a7bb4217a4` |

B's transmitted PCM is independently checked against its native-file PCM.
The whole reuse/retrigger sequence also repeats exactly with identical voice
history. CPU calls, card I/O and page delivery are modeled boundaries; the
loader notification events `[32,300]` and `[31,300]` are recorded by that
harness. This is not a coupled scheduling test of every notification consumer,
or proof that hardware always permits this unsafe sequence. It demonstrates
why slot clearing and allocation metadata alone cannot certify reader release.

Successful reports: `out/runs/recorder-reader-lifetime-20261021-03` and `-04`.
Retained failed controls: `-01` called an assignment helper on the wrong
adapter class; `-02` incorrectly compared a retrigger with a fresh engine's
voice/envelope history. The latter comparison is invalid while an old voice
can crossfade. The corrected test compares identical histories and retains the
unsafe-versus-unchanged-A negative comparison. The executed probe text is saved
in each run; no baseline expectation was regenerated.

## Final executable results

**PASS for the bounded native recorder → sequence → replace → queued FREEZE
workflow. Native DSP allocation/identity retirement remains blocked.**

Primary: `out/runs/recorder-freeze-queue-native-20261021-02/report.json`.
Exact repeat: `recorder-freeze-queue-native-20261021-03/report.json`.
Checks, worker/task/tick traces, native resource calls, retirements, heap
observations, snapshots and all voice PCM hashes match exactly between runs.
No host source HLE or host BUF commit executes. The adapter's old host FREEZE
method raises rather than silently substituting the diagnostic operation.

| Boundary / test | Observed result |
| --- | --- |
| GUI submissions | 269 attempts at `0x10701200`, task `0x40966ee8`, SR `0x2000`; NORMAL refused before queueing |
| FREEZE worker and body | 268 entries each at `0x10701600` / `0x10702000`, task `0x43172de4`, SR `0x2000`, host direct-call flag false |
| Completion | 268 original-service callbacks at `0x10701800`, GUI task `0x40966ee8`, SR `0x2000` |
| Shared native recorder worker | 11 original queued entries on the same worker TCB, preserving its prior admission/rollback tests |
| Four buffers / shared tracks | Five successful recordings; BUF 1 keeps slot 300 on T1/T5; frozen A at slot 312 survives B and subsequent generations |
| Active playback | Five original PLAY triggers while replacing A with B; prepared original SHARC replay preserves old readers and frozen A, and uses B on subsequent T1/T5 triggers |
| Source retirement | Five successful source frees each restore 16,384 buddy bytes; all eight issued source nodes end with a zero CPU PCM pointer |
| FREEZE ownership | Native cache-hit aliases only; no recording PCM capture, duplication or readback in FREEZE |
| Failure controls | Empty BUF, NORMAL, wrong epoch/kit, snapshot admission refusal, recorder's real heap refusal, post-alias rollback, metadata-only cache-miss rejection, duplicate serial, full registry |
| Full FREEZE registry | Eight snapshot identities issued, including two quarantined failures; 256 more actual queued requests return FULL without adding pages or sample identities |
| Refusal memory | CPU free bytes range `28,105,360..28,105,392` (32-byte variation); all sample lengths/keys and recorder ownership state remain exact |
| Native unit controls | 256 busy submissions preserve latched context; 256 full recorder admissions preserve all state; foreign-task mutations, in-flight operations, nested counter depth, argument order and SR restoration pass |
| Publication | `recorder-freeze-queue-publication-20261021-01`: one final logical header, original packet-boundary negative/rollback checks pass with `--require-atomic` |
| Regression | 345 unit tests; SINE replay; legacy managed Flex panel workflow; NORMAL stereo after BUF and NORMAL mono |

The eight immutable private DSP allocations remain pinned: 128 KiB for these
short fixtures, including three quarantined recorder candidates. Eight generation
and eight snapshot identities are consumed. FREEZE adds stock cache aliases and
fixed metadata, without another DSP PCM backing allocation. This is **not** a
hundreds-of-successful-re-recordings plateau: successful recording still stops
at eight issued generations. Its 20-second recorder bound is preserved; these
fixtures are about 3,120–3,184 stereo frames and do not measure 20-second throughput.

The original voice-output oracle remains byte-exact to ordinary-file loading,
including the previous worker's four hashes:

| Phase | Blocks | SHA-256 |
| --- | --- | --- |
| A plus frozen A | 12 | `655ca1fecf548431f21964e7f7dc7bb528e2e8a8197127f9c59b068f7c197fbc` |
| Old A during B publication | 12 | `d3090e584d94b23dbec40e3abe5857f3e8913cdbe336537eb410e9e63a3e2fdd` |
| New B and immutable A | 40 | `f3066ab5e61416ef6eec429a0584dd1e3442ca1c45d6bdd7ce7e3873d98dde72` |
| Late frozen A | 24 | `82785f2809238d040e3b07d8075800c711b660632d47948ba48ab80b27a746ed` |

These are voice work-buffer comparisons, not final DAC output, listening or a
coupled real-time timing result. The actual CPU PLAY capture and prepared DSP
replay are separate observations.

Additional reports:

- `recorder-freeze-queue-normal-20261021-01`: NORMAL after BUF, standard save,
  naming/cancel/file-error preservation, selector reassignment, E monitoring
  and independent stock reload. All eleven shared OLED captures are byte-exact
  to the preceding native-worker NORMAL-after-BUF run.
- `recorder-freeze-queue-normal-mono-20261021-01`: standard mono workflow with
  the new queue/operation wrappers installed.
- `recorder-freeze-queue-legacy-flex-20261021-01`: native replacement, control
  preservation, discard preservation and oversized-recording error/retry.
- `out/recorder-freeze-queue-unittest-20261021-02.log`: 345 tests pass.
- `20261021T103824Z-test-f2d2249d/manifest.json`: SINE replay passes.

Initial queue smoke attempts retained in `recorder-freeze-queue-smoke-20261021-01`
and `-02` failed the independent ColdFire instruction audit. Stack CLR, byte TST
and a quick-add form were replaced with already-reviewed MOVE/long arithmetic
forms. The auditor was not relaxed. Smoke `-03` proved task dispatch; `-04`
proved the added in-flight counter. The full `-02/-03` results above are the final
source-frozen candidate, including all ownership barriers and negative controls.

## Provenance and reproduction

Working-tree base: branch `codex/plaits-macro-controls`, HEAD
`77b1c2a1746a355b66b1a7e1cb61939c9bc0fdb5` plus the inherited uncommitted
experiments. HEAD alone does not reproduce this source tree.

- MAIN OS 1.16 SHA-256:
  `57bb4dfa8df07d846adc72fdb4fb0d3cd3c5680c524bf498338460207e008e7d`.
- Pinned DigiKit: `277760aad51b036a4756db051409d4d3b1eeccbc`.
- Pinned Selache: `2b26d3b75c53063575bc5c820fa0d38879335187`.
- Final 584-source manifest SHA-256:
  `6f6afc894c392b623020c3aafac3135f8a828f5429543cd9b8e546f2bf0e8c0b`.
- Audit: `out/runs/recorder-lifetime-audit-20261021-01/`; includes before/after
  source and test hashes, preservation checks, emitted payload hashes,
  exact-repeat checks and final verification. Each main workflow run saves
  the source text it actually executed under `frozen-sources/`.

Of 581 inherited source files, 578 remain byte-exact. Only the native FREEZE
emitter (optional guarded-body generation), native-worker test and NORMAL test
were extended. Three new implementation/probe files were added. All 53 inherited
unit files are byte-exact; one new file adds eleven tests. The original default
FREEZE payload is byte-exact, including all resource/project/slot handlers;
its body SHA-256 remains
`3a17277ae7baaf960b9fc4003855342d10d28badb7511806133d817898f5ef7d`.
The new queued payload emits 1,976 bytes into its 16 KiB emulator mapping.
Normal builders, firmware placement, dependencies and shortcut sources were
not changed. No hardware transfer, flash, commit or publication was performed.

From the repository root, using fresh output names:

```sh
PYTHON=$(python3 -c 'import json; print(json.load(open(".local/config.json"))["python"])')
./labctl doctor
"$PYTHON" scripts/check-recorder-worker-native.py out/runs/freeze-queue-repro-01 --queued-freeze
"$PYTHON" scripts/check-recorder-worker-native.py out/runs/freeze-queue-repro-02 --queued-freeze
"$PYTHON" scripts/check-recorder-worker-publication.py out/runs/freeze-queue-repro-01 out/runs/freeze-queue-publication-repro --require-atomic
"$PYTHON" scripts/check-recorder-reader-lifetime.py out/runs/reader-lifetime-repro-01
"$PYTHON" scripts/check-recorder-reader-lifetime.py out/runs/reader-lifetime-repro-02
"$PYTHON" scripts/check-recorder-normal.py out/runs/freeze-normal-repro --queued-freeze --prebuffer
"$PYTHON" scripts/check-recorder-normal.py out/runs/freeze-normal-mono-repro --queued-freeze --mono
"$PYTHON" scripts/check-flex-native-ui.py out/runs/freeze-legacy-flex-repro --managed-sources
"$PYTHON" -m unittest discover -s tests -v
./labctl test sine --replay
```

## Remaining gates and next prototype

The next bounded increment is now recorded in
[RECORDER-RETIREMENT-OBSERVER-RESULTS.md](RECORDER-RETIREMENT-OBSERVER-RESULTS.md):
native ColdFire request construction and an advisory native SHARC reader
observer pass exact stock-output comparisons. A native return carrier and
queued-control/root closure remain unresolved; no allocation or identity reuse
is enabled. The original results and finite worker policy below remain intact.

1. Audit a non-conflicting CPU→DSP request and DSP→CPU acknowledgement carrier,
   including its producer, consumers, capacity and ordering. Preserve the
   existing Capicola reply field and transport frame size. There is no verified
   native generation-specific retirement acknowledgement in this candidate.
2. Add a bounded original-SHARC reader-observer experiment for ONESHOT first.
   Identify the final old read/block boundary across all 32 lanes and any queued
   triggers. Prove delayed, lost, duplicate and stale acknowledgements against
   the host observer oracle. An acknowledgement left in emulator memory is not
   a completed native transport.
3. Connect that acknowledgement to ColdFire admission and private-slot release,
   with immutable snapshot/root pins and epoch/sequence matching. Reclaim
   backing before considering identity recycling. Only then run hundreds of
   successful re-recordings with a fixed set of snapshots and demonstrate a
   bounded DSP/CPU plateau. Preserve the current finite implementation as a
   fallback.
4. Close other machine reader lifetimes and all project/pattern/sample-lock/
   queued-event roots before broadening the ONESHOT claim. Known volatile
   save/load guards are not a complete project-transition protocol.
5. Bind next-bar arming only after proving a real sequencer master-bar edge.
   The previous conditional counter was not such an edge; explicit test-bar
   events remain insufficient. Shortcut prototypes are preserved and unbound.
6. Native SAVE still requires DSP PCM readback and a readback lease. FREEZE
   remains an immutable volatile alias, not a persisted file. Target memory
   placement, coexistence with the combined image, coupled capture/transport,
   cache/peripheral behavior and physical deadlines remain unverified.
