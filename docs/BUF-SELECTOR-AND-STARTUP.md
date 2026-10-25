# BUF selection and startup loading — OS 1.16

The user reports that the latest clock-correction firmware now works on their
Digitakt II. This is a user-reported device result for that trial, without an
independent installed-image readback or timing measurement. The next requested
work is reducing the startup recording wait and placing BUF 1–4 immediately
before A00 OFF in the normal sample selector.

This pass investigates those two paths. It adds a read-only survey script and
these findings; it does not change firmware behavior or produce a new image.
The working clock package remains SHA-256
`7fcf8653b0aeb81204b7d0bc3b10d1419dac90f677fc097dfe11d5165988693d`.

## Startup: slots and shared memory are separate concerns

**Evidence:** BUF already reserves four logical sample slots and eight private
generation slots. `recorder_worker_code.setup` scans the existing 1,024-slot
namespace, excluding each bank's OFF entry and checking the project reference,
loader key and readiness tables. These are twelve metadata slots, not twelve
recording buffers or twelve fixed PCM regions. The prepared project reserves
300–303 for BUF 1–4 and 304–311 for generations; another project can choose
different free slots.

The ARM refusal occurs *before* that setup: `buf_next_bar.arm_only` rejects an
active sample operation (`q.STATE+56`) or stock loader busy flag
(`0x405b1360`). `initialize_buffers` has the same exclusion. A different slot
number or CPU code address does not change those predicates.

The stock loader at `0x40154540` checks slot <=1023, sets the global busy flag,
and uses the shared allocation vector at `0x405a0f64` and slot-to-allocation
table at `0x405b5368`. Its allocation paths can grow/reorganize that vector;
unload also changes it. Therefore disjoint *slot numbers* do not establish
independent allocator ownership. The loader emits sample/header transfers
through the same playback infrastructure used by BUF publication.

The earlier [saved startup trace](../out/runs/sketch-sample-diag-native-20261023-01/startup-operations.json)
observes 297 outer loads, with 259/261/262 among them and caller return
`0x4004eaae`, inside the project load worker's per-slot loop. It was not a
FREEZE backlog. The user later confirmed that waiting clears the refusal.
This pass reads that existing evidence; it does not run another cold boot.

**Important boundary:** these guards test an operation in progress, not a
"whole project finished loading" latch. A zero count between two pending loads
does not by itself prove the load batch is complete. Existing capture lease
value 1 also forwards stock operations; the guards are not a whole-batch lock.
An automatic retry must be tested with later loads still pending.

**Inference:** inventing slots 1024–1027 would require changing several CPU,
project, selector and DSP consumers. Reserving the last four ordinary slots
instead risks real project references and still shares the allocator. Neither
is the small solution to this wait. An independent PCM arena would be a larger
memory/loader design, not simply four new addresses.

There are two different improvements:

1. **Remember ARM while loading.** Keep one bounded pending request with BUF,
   project/kit/epoch and capture settings latched. Revalidate at safe native
   admission, then start on the next qualified bar. STOP/NO, changed settings
   or project replacement cancel it. This removes the repeated button press;
   it does not promise immediate capture or bypass a busy operation.
2. **Capture before publication is available.** Separate recorder ownership
   from sample-pool mutation. Capture into stock recorder storage first, retain
   that take, and copy/load/publish later through the existing worker after
   safe admission. This is the promising route to actual earlier recording.
   It needs proof of recorder readiness during startup, retained source lifetime,
   initial slot reservation, queued-load interleavings and publication failure.
   No source scratch may be treated as owned immutable PCM. Internal resampling
   can only capture the sound actually available while other samples load.

**Unresolved:** neither improvement is implemented or qualified here. First
probe ARM at a real between-load boundary with further loads pending, then
follow capture and publication without clearing either guard. This determines
whether a pending-request frontend suffices or a new staging phase is needed.

## Native selection: four UI aliases before A00

**Evidence:** the encoder-D quick list is `SampleListView`, not the full
`SamplePicker` browser. Both exist in stock RTTI. Relevant OS1.16 seams:

| Seam | Address / meaning |
| --- | --- |
| Quick-list draw | `0x4001e78a` |
| Quick-list keys | `0x4001ebc8` |
| Quick-list row formatting | `0x4001dfbe`, bank/row to ordinary sample name |
| Quick-list selected-slot conversion | `0x4001e17a`, current menu row plus bank |
| Quick-list close/cancel | `0x4001e1fe`; NO can restore its original sample through the existing callback |
| Quick-list bank parameter callback | `0x4001df34`; native sample parameter ID `0xcd` |
| Sample-pool name provider | `0x400164e0` |
| Full browser primary vtable | `0x401ee1c4` (RTTI table header `0x401ee1bc`) |

The prepared native panel survey confirms:

- UP from A00 clamps at OFF; a further UP remains slot 0.
- RIGHT from A00 reaches B00 (slot 128); LEFT returns A00.
- DOWN then YES retains A01 (slot 1).
- An **empty** BUF 1 is already selectable at its backing slot: this fixture's
  list shows `044 BUF 1` in bank C. YES retains slot 300 without a recording or
  publication. The source page's compact sample field subsequently shows C44.
- The track's sample parameter changes while browsing. YES is not the only
  point where mapping matters; NO/restore and native parameter/lock handling
  must receive backing slots throughout.

[Native screenshots](../out/runs/buf-selector-startup-investigation-20261023-03/selector-contact.png)
and [panel trace](../out/runs/buf-selector-startup-investigation-20261023-03/selector-trace.json)
record this existing behavior. The quick-list, full-browser, pool-name and
project-sample-access bytes match the working clock candidate exactly.

**Recommended design:** add four selector entries as aliases of the existing
logical BUF mapping (`recorder_freeze_code.STATE+32`), not as new playback
identities. Counter-clockwise from A00 reaches BUF 1, then 2, 3 and 4;
clockwise returns through A00 to A01. A temporary menu rank belongs to the view;
only a resolved valid backing slot enters the native sample parameter.

Thus existing A–H numbering, OFF, track storage and DSP lookup remain intact.
Render BUF labels/status directly from logical identity, including EMPTY and
READY, and show `BUF 1` instead of C44 in the compact SRC field when appropriate.
Do not change lengths or manufacture an allocation to make an empty BUF visible.
The backing row may remain reachable in its ordinary bank as an alias; that
does not create another take. FREEZE snapshots keep their existing separate
selection for this first slice. The full browser must map the same identities,
even if its first presentation remains in the ordinary backing bank.

**Unresolved implementation seams:** quick-list rank/row creation, encoder-D
entry at A00, inverse mapping when reopening an assigned BUF, bank switching,
NO restoration, parameter locks and compact SRC formatting must agree. Do not
pass negative virtual ranks or values >=1024 into stock sample accessors.
BUF setup can still be unavailable during loading or when fewer than twelve
eligible slots remain. A UI alias does not add sample capacity or persistence.

## Next implementation and focused acceptance

Implement the opt-in native quick-selector aliases first, against the working
clock profile, with clear EMPTY/READY labels and compact BUF names. Keep actual
slot allocation, publication, FREEZE and retirement unchanged. Check all four
empty/ready identities, A00 boundaries in both directions, fast encoder turns,
ordinary bank boundaries, reopen/NO restoration, native locks and two tracks
sharing a BUF across replacement. Recording must never assign a track.

Keep startup work as a separate experiment: active and nested sample operations,
between-load gaps with pending work, STOP/NO/project/settings cancellation,
recorder source retention, memory exhaustion and failed publication preserving
the previous BUF. Success must include ongoing normal sample loading, not just
a prepared idle fixture. Physical startup timing still requires a device trial.

## Reproduction and limits

`./labctl doctor` passes. The read-only static survey authenticates exact stock
MAIN SHA `57bb4dfa8df07d846adc72fdb4fb0d3cd3c5680c524bf498338460207e008e7d`,
extracts RTTI/disassembly and checks relevant selector bytes against the saved
clock build. Unknown MAIN bytes are rejected. Use the configured interpreter:

```sh
"/Users/lanceship/Documents/Codex/Digitect firmware research project/work/digikit/.venv/bin/python" \
  -B scripts/investigate-buf-selector-startup.py out/runs/YOUR-SELECTOR-SURVEY \
  --clock-build out/runs/sketch-clock-build-20261023-02
```

The exact panel probe is retained in
`out/runs/buf-selector-startup-investigation-20261023-03/probe-selector.py`.
It uses the existing prepared Python/Unicorn Sketch adapter, native CPU menu
instructions and modeled peripherals. It does not run SHARC audio or establish
physical timing, preview audio, every bank/lock case or the proposed four-row UI.

The first probe failed because its harness sent an out-of-range encoder delta;
the second is explicitly unqualified because it did not await recorder readiness
and closed the auto-opened list before sending arrows. Both are retained. The
third waits for native reservations, navigates the actual list and asserts A01,
empty BUF assignment, no publication and released worker ownership. Independent
report checks verify the OFF/bank boundaries from its saved state observations.
No new recording, firmware build, package, hardware transfer, commit, dependency
change or upstream edit was performed. No DSP/adapter behavior changed, so a
new audio replay or unrelated feature suite is unnecessary for this survey.
