# Recorder and live buffers: product handoff

Target: Digitakt II OS 1.16. Local investigation, 2026-10-20. This supersedes
the two-recorder-page idea as a product proposal; it does not replace the
existing implementation. See the companion
[FREEZE evidence report](RECORDER-BUFFER-FREEZE-RESULTS.md) for executed results.

## Decision

Keep one stock recorder page. Encoder C selects **NORMAL | BUF 1 | BUF 2 |
BUF 3 | BUF 4**, initially NORMAL. MON remains on E. Record, commit, freeze and
save are separate operations. FREEZE preserves a version as a new immutable
Project RAM sample; the original buffer remains recordable. Saving to +Drive
is a later, explicit operation. No automatic intermediate files.

The existing emulator still says **TAKE**, not NORMAL. Changing that label
would conceal a different YES handler, not restore stock sampling. Do not
ship that substitution or delete native Flex yet.

## Audit: exists, missing, risky

Audited branch `codex/plaits-macro-controls`, HEAD
`77b1c2a1746a355b66b1a7e1cb61939c9bc0fdb5`, with substantial inherited dirty
work. HEAD alone does not describe the tested implementation. Initial status,
556 source hashes and prior report hashes are in
`out/runs/recorder-handoff-audit-20261020-01/`. All 556 sources matched the
successful encoder-C workflow's manifest at audit time. DigiKit and Selache
remain at the revisions in `deps.lock.json`; neither dependency is edited.

| Exists and evidence | Missing | Consequence |
| --- | --- | --- |
| `lab/flex_buffer_ui.py`: emitted C setter/draw in mapped emulator RAM; stock recorder, trim, MON E and sample selector | Target-reserved code/state and native publication transaction | This is an opt-in emulator adapter, absent from normal firmware builds |
| Four stable visible buffer slots; T1/T5 assignment through stock selector; BUF USE autoassigns selected ONESHOT track | Other machines, sample locks, dormant patterns, queued events, clipboard/undo roots | ONESHOT results cannot establish compatibility for SLICE/GRID/WERP/REPITCH/STRETCH |
| CPU loader/LP0/SHARC output parity with source retired; second allocation published during old playback | Native DSP readback, native source-free resolver, reader completion protocol | Resident playback works; reopening/saving/reloading the removed source does not |
| Private stock allocation pins and bounded admission: eight generations, 4 MiB, two seconds per candidate | Safe generation reclamation and indefinite recording | Memory grows to a deliberate refusal; this is not a memory plateau |
| Original 20-second Flex implementation and managed saved-source retirement preserved | Unsaved source retirement integrated into that implementation | Removing TAKE from the display would not fix CPU duplication |
| Guarded project save/load entry points and modeled epoch invalidation | Complete project/pattern serialization and real transition barriers | Do not claim volatile audio survives project load or restart |

Prior executed reports: `flex-dsp-memory-20261020-03`,
`flex-buffer-c-workflow-20261020-02`, `flex-buffer-c-audio-20261020-01` under
`out/runs/`. The first runs real native CPU source free; the buffer UI uses a
host-backed source provider and removes its PCM entry after loading. These
are different evidence layers. Host WAV fixtures and captured pages are test
artifacts, not persistent device backing.

## Interaction map

| Context / action | Recommended behavior | Implementation status |
| --- | --- | --- |
| SAMPLING | Open the existing recorder | Stock page used by current prototype |
| Recorder C | NORMAL, BUF 1–4; show selection on subsequent visits | C works for TAKE/BUF; NORMAL routing remains a migration gate |
| Recorder A/B/D/E/F/G/H | Preserve current source/channel/threshold/monitor/length/start/arm controls | C prototype leaves MON E and trim E/H on original paths |
| NORMAL record/trim/YES/shortcuts | Complete original naming/save/assign flow | Must run with original handler and labels; not satisfied by TAKE |
| BUF record/trim/USE | Stage candidate, publish completely, commit latched destination | Host transaction exists; retain previous version on cancel |
| BUF USE assignment | Keep autoassignment for first prototype; never reassign other tracks | Matches current Flex convention; compare commit-only below |
| Sample selector | BUF 1–4 alongside ordinary samples; frozen names e.g. B1-001 | Buffer rows exist; FREEZE experiment extends stock rows |
| Sequencer double SAMPLING with BUF selected | Toggle arm; next bar starts capture; fixed previously selected length; automatic commit after complete publication | Future native shortcut; isolated state-machine contract only |
| Same gesture in NORMAL | Original behavior | No interception installed |
| Fast FREEZE | Snapshot the selected buffer's committed version; brief B1-001 feedback, no page change or autoassignment | Gesture deliberately unbound pending collision audit/approval |
| FUNC+SAMPLING management | Eventually +Drive / Project RAM / Record Buffers | Proposed organization, no new manager implemented |

Latch buffer, source, channel, duration and project epoch when arming. Encoder
changes after arming apply to the next recording. Initial quick-record policy:
only arm while the sequencer is playing; STOP cancels an arm or discards an
unfinished candidate. Commit immediately after full publication, not on a
second guessed bar boundary. Readers already playing keep the old generation;
new triggers after commit see the new one. Transport delay is not yet measured
on hardware. Do not promise sample accuracy.

`lab/flex_quick_record.py` deliberately models only integer bar durations
with supplied bar events and completion tickets. Stock R.LEN uses steps (or
MAX); mapping every length, scale, clock and source to native capture remains
unimplemented. `lab/pattern_clock.py` supplies modeled SSI cadence and guest
IRQ delivery, not an authoritative musical-bar notification. The arp's
`0x4002d744` tempo getter and private phase accumulator likewise cannot be
substituted for the sequencer's bar position. Tests of this isolated contract
do not establish acceptance scenario E on the panel.

On manual USE, autoassignment is convenient when initially capturing material
for the selected track. Once T1 and T5 already share BUF 1, both update through
the logical buffer without any extra assignment. Autoassignment can still
replace an unrelated selected track's sample. Commit-only avoids that surprise
but requires initial manual assignment. Keep the tested convention during
this investigation; compare a session preference later. Quick-record and
FREEZE should commit/create resources without changing track assignments.

## Shortcut candidates and collision analysis

The pinned panel map reports SAMPLING=50, FUNC=17, YES=10, NO=12,
STOP=21 and encoder-C push=43. C *rotation* is an independent event space;
an unused rotation on the recorder does not prove C push is globally free.
`lab/flex_buffer_ui.py:rotation()` only adds C to the ready/armed recorder
dispatch at `0x400209ae`. It does not intercept transport or global keys.

The existing 128×64 display places DEST at (80,27), centered value at (80,39),
replacing C's ready-page REC NOW / YES graphic. It uses stock fonts
`0x402a6c30/0x402a96a0` and scaler `0x40111b62`, not a new parameter page.
Guest state at the emulator-only scratch `0x10300000` survives recorder visits
within the session; it is not a safe target reservation or a saved project
parameter. A new project should start at NORMAL. Trim keeps its original E/H
controls.

Static 1.16 checks in the audit directory establish event key at `+0x0c`
(`0x401146a4`) and flags at `+0x10` (`0x401146ae`); helpers test bit 0
(`0x401146fc`), bit 1 (`0x40114738`), bit 3 (`0x40114708`) and bit 4
(`0x401146cc`). These tests alone do **not** prove the generation, timing or
consumption of double taps. Key-50 dispatch leads at `0x4002960a → 0x400296d0`
and `0x40064a5e → 0x40064c3e` already branch through modifier/phase helpers.
The held-state query `0x4011de70` reads the panel's bit map. These are leads
for a focused event trace, not proof that a new chord is free. The new probe
does not patch these routines.

The official [OS 1.15A manual, sampling and sample management sections](https://www.elektron.se/wp-content/uploads/2025/07/Digitakt-2-User-Manual_ENG_OS1.15A_250708.pdf)
documents FUNC+SAMPLING for sample management, and SAMPLING+YES/NO for
arming/canceling. This is supporting UI evidence from 1.15A, not proof of all
1.16 handlers. The local native Flex save extension also uses FUNC+RECORD
contextually. Preserve these gestures and double-STOP.

| Candidate | Collision / usability | Decision |
| --- | --- | --- |
| Double SAMPLING | Proposed quick-record arm already needs it; first press normally opens sampling | Reserve for quick arm investigation; not FREEZE |
| FUNC+SAMPLING | Existing sample-management navigation | Keep unchanged |
| Double STOP | Existing audio stop/panic behavior | Keep unchanged |
| FUNC+RECORD | Grid/live recording and existing Flex save contexts | Reject as a global FREEZE override |
| SAMPLING+YES | Existing recorder arm shortcut | Keep unchanged |
| Hold SAMPLING, press encoder C | Distinct from C rotation, one held key plus nearby push, could refer to current DEST; unknown combined-key consumption and first-press navigation | **Preferred candidate for approval after event trace**; no binding installed |
| Contextual FREEZE action on a buffer SRC page | Discoverable fallback, but consumes a contextual action and needs sample-reference resolution | Compare if the held-key chord cannot preserve navigation |

For the preferred candidate, postpone the SAMPLING single action only when a
buffer is selected and the sequencer is in an eligible performance context.
A short tap must still open sampling; the chord must not also open a page or
arm a recorder. This requires evidence of event ordering, held-key state and
single/double arbitration, not only a check for a spare flag bit. A unified
arbitrator must also distinguish the quick-arm double tap. No physical gesture
has been approved or implemented here.

## Ownership and persistence

| Entity | Owns / retains | Replacement rule |
| --- | --- | --- |
| Project-scoped logical BUF n | Current immutable generation | Change only after complete publication |
| Candidate | Bounded capture/trim staging and latched epoch/destination | Discard never changes the committed generation |
| Physical SHARC PCM allocation | Published channels plus interpolation guards | Never overwrite while any reader or alias might need it |
| Frozen Project RAM sample | Distinct immutable logical identity, slot and generation pin | Does not follow subsequent BUF commits |
| Active/queued reader | Specific resolved generation | Reader completion must be acknowledged before reuse |
| CPU source/staging | Loader input, not a CPU pointer usable by SHARC | Release PCM after publication only with a correct metadata/reopen policy |
| Persistent file | Verified standard sample bytes and durable identity | Only explicit successful Save can replace volatile ownership |

One allocation can potentially back BUF 1, a private generation pin and a
frozen sample simultaneously. Distinct logical identities do not require
distinct PCM. The stock loader's cache key and allocation reference are not
the same as a new project snapshot identity. The bounded FREEZE experiment
tests this distinction; it cannot establish complete native reference counting.

Keep all generations quarantined in the first prototype. This protects old
voices and unknown late roots at the cost of eventual refusal. A zero-active-
voice observation does not release sample locks, old patterns, preview,
clipboard, queued trigs, future snapshot assignments or in-flight DMA. No
timeout-based reuse. No identity recycling. Capicola's 8 MiB is untouched.

Both buffers and snapshots are volatile for now. Block project persistence
when it would produce missing audio; do not report success after dropping
volatile roots. Native readback is a separate dependency for Save, so do not
expose a working Save item yet. Real project transitions require canceling
pending work, draining publication/readers, invalidating epoch-scoped handles,
then releasing only proven-unreferenced storage. The host epoch test is not a
native project-load implementation.

## TAKE migration gates and next increments

1. Preserve the old TAKE path and its 20-second regression fixtures. Add an
   opt-in NORMAL branch that bypasses USE interception and restores original
   trim labels/save handlers, while keeping the new C cell. Exercise original
   naming, cancel, assign, shortcuts and file failure. Only then hide TAKE from
   the new UI; keep it available in the old experimental build/test path.
2. Prove FREEZE using a new logical slot retaining a completed allocation;
   verify exact stock PCM after BUF replacement, no PCM pages or allocator
   growth on freeze, empty/stale/exhaustion failures and snapshot selection.
3. Implement a native volatile metadata resolver and protected alias roots.
   A cache miss must fail safely rather than try to reopen missing PCM. Define
   snapshot limits, deletion and accounting before relaxing the experiment's
   fixed caps. Do not call aliasing a solution to native Save.
4. Trace global SAMPLING key dispatch, flags, held chords, clock phase and
   bar/length notifications with internal/external clock and scale changes.
   Prototype quick recording only after those boundaries are authoritative.
   Until then test an isolated scheduler contract with injected bar events.
5. Establish readers/queued events/locks/project roots and native retirement
   barriers. Then test actual reuse rather than retaining every generation.
6. Implement native bounded readback or another verified Save path, including
   file failure and stock reload parity. Add explicit Save/Freeze/Clear in the
   management view and define project durability. Only after this supersedes
   legacy behavior consider removing the underlying TAKE implementation.

Remaining target gates include physical timing, input/internal-mix producer,
DMA completion/cache visibility, hardware controls, all playback machines,
power loss and project reload. None is established by host callbacks or
instruction counts. No firmware installation image is produced by this work.
