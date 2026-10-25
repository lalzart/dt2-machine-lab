# Native recorder / FREEZE vertical slice — OS 1.16

2026-10-20. See [the plan and native ABI](RECORDER-FREEZE-NATIVE-PLAN.md).
These are isolated emulator changes. No normal firmware build, dependency,
legacy Flex implementation, hardware state or historical baseline was changed.

## Gate status

| Gate | Status | Evidence boundary |
| --- | --- | --- |
| A stock NORMAL parity | PASS | Original record, E/H trim, name/save/cancel, assign, selector, E MON and file-error logic execute; mono/stereo storage, PCM and nine OLED states match stock |
| A recheck with B installed | PASS | Same exact comparisons with native resource/slot/project thunks; NORMAL after BUF 1 also succeeds |
| B metadata-only FREEZE | PASS for the bounded diagnostic | Executed ColdFire registration, identity/epoch/key resolution, stock slot association, native name publication, rollback/quarantine and persistence/slot guards; exact original SHARC voice output |
| C performance binding | DECISION PENDING | Untouched-stock chord trace completed; no key is installed without user selection |
| Native recorder backend / device integration | NOT COMPLETE | BUF capture/commit is host-assisted; diagnostic uses paused worker/IPL 7 and emulator scratch; target timing/placement unresolved |

The product model is **NORMAL | BUF 1–4**, using the same recorder and C cell.
Historical TAKE remains available in its previous implementation/experiments.
Nothing removes or repackages the native 20-second Flex path.

## Source and reproduction identity

Audited branch `codex/plaits-macro-controls`, HEAD
`77b1c2a1746a355b66b1a7e1cb61939c9bc0fdb5`, plus inherited dirty work.
`out/runs/recorder-native-audit-20261020-01/` retains initial Git status,
560 source hashes/copies and the supplied task SHA-256. All 560 pre-existing
source files remain unchanged. The prior host FREEZE proof's source manifest
still matched at task start; it was not replaced or relabeled native.

The final native proof freezes 567 sources. Its `report.json` SHA-256 is
`0460f203f63620645c27fc843c942a78c7921f6c27ad5ed315cc469021de2883`;
`sources.json` SHA-256 is
`f0697fb0097cd5846fd2f6d8f7f7d48179e3071af79037f7beb4aed5cb9ede74`.
Pinned clean DigiKit remains `277760aad51b036a4756db051409d4d3b1eeccbc`,
Selache `2b26d3b75c53063575bc5c820fa0d38879335187`. `./labctl doctor` passes.

Authenticated MAIN is
`57bb4dfa8df07d846adc72fdb4fb0d3cd3c5680c524bf498338460207e008e7d`.
The existing `stock_inputs()` authenticates the ready checkpoint, card and
LP0 feed; the independent file reload snapshot is
`175982f14b371fafe0eb54f2943167a94f71370327e65c7fe9941b1336bbc301`.

New code, all opt-in:

- `lab/recorder_normal.py`: stock recorder peer / NORMAL branch, lazy buffer
  setup and native reserved-slot filter.
- `lab/recorder_overlay.py`: explicit eMMC byte-map → sector-map conversion.
- `lab/recorder_freeze_code.py`: independently audited ColdFire emitters.
- `lab/recorder_freeze_native.py`: experiment installation/diagnostic adapter;
  host source HLEs disabled while native metadata commands execute.
- `scripts/check-recorder-normal.py`, `check-recorder-freeze-native.py`,
  `trace-recorder-freeze-gesture.py`.
- Two new test files: overlay conversion and executed native metadata/ABI.

Run from the repository root with configured Python 3.12. Public launchers
re-exec that interpreter. Use fresh output names; private existing fixtures
are required. Gate B requires the Gate-A pass record, produced by comparing
the original/candidate reports; the retained record is in the audit directory.

```sh
./labctl doctor
python3 scripts/check-recorder-normal.py out/runs/NEW-STOCK --stock
python3 scripts/check-recorder-normal.py out/runs/NEW-NORMAL
python3 scripts/check-recorder-normal.py out/runs/NEW-STOCK-MONO --stock --mono
python3 scripts/check-recorder-normal.py out/runs/NEW-NORMAL-MONO --mono
python3 scripts/check-recorder-normal.py out/runs/NEW-AFTER-BUF --prebuffer
python3 scripts/check-recorder-freeze-native.py out/runs/NEW-NATIVE-FREEZE
python3 scripts/check-recorder-normal.py out/runs/NEW-NATIVE-NORMAL --native-freeze
python3 scripts/check-recorder-normal.py out/runs/NEW-NATIVE-MONO --native-freeze --mono
python3 scripts/check-recorder-normal.py out/runs/NEW-NATIVE-AFTER-BUF --native-freeze --prebuffer
python3 scripts/trace-recorder-freeze-gesture.py out/runs/NEW-GESTURE-TRACE
"/Users/lanceship/Documents/Codex/Digitect firmware research project/work/digikit/.venv/bin/python" -m unittest discover -s tests -v
./labctl test sine --replay
```

## A: actual stock NORMAL

The new adapter bypasses the earlier host USE transaction in NORMAL and keeps
original `Y:SAVE`. Recorder command-4 input follows the existing native peer's
recursive-lock observation. Naming, writer `0x40153994`, files, original loader
and assignment run as firmware instructions. Only recorded input and low-level
sector I/O are modeled; file open is overridden solely for the named failure
injection. Mono uses the same pre-record MONO-R settings seed in both fixtures,
not a claim of testing physical CHAN rotation.

Final A runs: `recorder-normal-{stock,candidate}-20261020-04`,
`recorder-normal-{stock,candidate}-mono-20261020-01`, and
`recorder-normal-after-buffer-20261020-02` under `out/runs/`.
`recorder-native-audit-20261020-01/gate-a.json` records the exact pair comparisons.
The candidate remains lazy: fresh NORMAL does not initialize buffer resources.
E/MON changes 0→1 through original encoder handling. Original E/H trim moves
the deterministic 2,400-frame capture to [66,2334). Filename cancel has no
write; UP edits REC0000 to SEC0000; original SAVE and TRIG 1 assign it.
Independent stock reload matches PCM. Selector reassignment and injected
file-open failure preserve the previous track and storage.

The after-BUF test originally failed with LOAD ERROR: slot 301 was both
stock-free and reserved for BUF 2. The native search-loop filter now skips
the four logical and eight private rows, using the original capacity and
project-reference checks. NORMAL chooses 304 while BUF 1 remains at 300.
No fake persistent identity is written to reserve an empty row.

B-installed rechecks: `recorder-native-normal-{stereo,mono,prebuffer}-20261020-01`.
Their storage overlays, PCM, reference, trim, writes and nine non-DEST OLED
states match the untouched stock controls. The prebuffer case again chooses
304. `recorder-freeze-native-20261020-03/normal-parity.json` records this check.

## B: what is native

`recorder-freeze-native-20261020-03` executes:

1. Original recorder UI/C chooses BUF 1; existing host-assisted USE publishes
   A and removes its source PCM entry. A native call registers metadata from
   the CPU's actual immutable cache key.
2. Native `freeze(1, epoch, expected_kit)` checks preconditions and derives the
   project pool, calls the original free-slot iterator and stock sample loader,
   associates slot 304 with the resident generation, writes `B1-001` into the
   stock name tables, and publishes its distinct logical project ref last.
3. Original selector assigns BUF 1 to T5 and B1-001 to T6. The snapshot slot
   is checked in an actual CPU-produced control frame. FREEZE itself makes
   no track assignment or file write and opens no browser/dialog.
4. B replaces BUF 1's physical backing. T1/T5 retain logical slot 300; T6
   retains 304 and its immutable A allocation. Old private pins remain.
5. Native rollback/error controls and eight recording generations exercise
   refusal, tombstones, native slot protection and native project guards.

Native resource resolve returns exact status **1** only for the full registered
reference and epoch. Key returns the original immutable generation key. Native
name/open/read/size/close semantics are independently executed by unit tests;
unsupported full-source operations reject. The cache-hit workflow chiefly uses
resolve/key; a deliberate cache miss reaches native OPEN and is refused.
Stock cache hits retain the original generation name, so snapshot naming is a
separate native write into the original inline/name-pointer tables.

The adapter checks that no host source HLE was called during **any** native
registration/FREEZE/guard diagnostic transaction. Host HLEs remain available
for the earlier BUF input/commit loader. All new emitted instructions pass
the existing CFPRM-based auditor before execution; authenticated stock entry
prologues are separately classified as copied stock trampolines. Guards and
code ranges are retained in `native-patches.json` / `code-ranges.json`.
Four executed-unit scenarios additionally check callee-saved registers, key
preservation, exact-reference corruption, epochs/tombstones, no PCM handles,
ordinary file fallback and refusal to reuse an issued generation identity.
`instruction-audit.json` records 811 independently decoded new B instructions
across the metadata/command/guard functions; A's slot filter is also audited
by its emitter. Copied stock prologues remain explicitly separate.

## Native failure controls and memory

| Control | Native outcome |
| --- | --- |
| Empty buffer | −2; no new snapshot |
| Stale epoch / same kit address with a different epoch | −3; previous tracks unchanged |
| Snapshot identity collision / admission seam / issued limit | −5; no replacement |
| After alias but before project publication | −4; unload/clear new slot, tombstone ID, quarantine slot |
| Changed cache key forcing stock loader reopen | Native OPEN rejects; −4 cleanup, no PCM source fallback |
| Invalid/empty header stage without completing alias | −4 cleanup; no project reference or selectable broken sample |
| External unload/clear of a frozen slot | Native guards preserve allocation/slot |
| Save/load project with volatile audio | Native entry guards return failure before writes |

The staged incomplete-publication control is not a test of physically lost
DMA/LP0 traffic. Stock transport delivery/completion remains modeled; no new
hardware acknowledgement protocol is implemented. Real allocator failure
inside the stock loader, whole-device pressure and all asynchronous races are
unresolved. The admission seam tests native refusal, not measured heap OOM.

Eight recording generations retain 131,072 DSP allocation bytes. Each successful
freeze emits **two headers and zero PCM pages**, shares the original allocation,
and consumes **32 bytes of stock CPU heap** for its association node. In
addition it occupies a preallocated **64-byte native snapshot record**. The
32-generation/eight-snapshot descriptor tables occupy 2,560 bytes in the mapped
workspace, plus state/names/code. The whole 32 KiB emulator mapping is not a
target memory reservation and is not included in the heap delta.

Eight snapshot IDs are issued: **five ready and three quarantined failures**.
B1-001 is at 304; failed 002–004 occupy protected identities/slots 305–307;
later ready names start B1-005 at 308. IDs and failed slots are never recycled.
All generation PCM remains pinned. No memory plateau or indefinite reuse is
claimed; Capicola's 8 MiB and existing sample-pool bounds are unchanged.

## Original SHARC output and negative oracle

Actual captured page histories and CPU controls are replayed through original
SHARC LP0 callbacks and ONESHOT rendering, against the original ordinary-file
CPU loader. Output is the existing voice-work-buffer tap, not final DAC output
or concurrent real-time processor execution.

| Phase | 32-frame blocks | Exact float output SHA-256 |
| --- | --- | --- |
| A buffer + snapshot | 12 | `655ca1fecf548431f21964e7f7dc7bb528e2e8a8197127f9c59b068f7c197fbc` |
| Active A while publishing B | 12 | `d3090e584d94b23dbec40e3abe5857f3e8913cdbe336537eb410e9e63a3e2fdd` |
| New B on T1/T5, A on T6 | 40 | `f3066ab5e61416ef6eec429a0584dd1e3442ca1c45d6bdd7ce7e3873d98dde72` |
| Late snapshot trigger after eight generations | 24 | `82785f2809238d040e3b07d8075800c711b660632d47948ba48ab80b27a746ed` |

All three tracks are nonzero. Active A pointers stay `0x8422d9e8/0x8422f9e8`
across B publication. WAVs, float output, `a-pad.dtfr` and page histories are
retained in the run. `selector-t6.png` shows B1-001 in the stock selector;
`02-new-buffer-and-native-frozen-a.png` shows the later state. Untouched NORMAL
and candidate screenshots are in their respective Gate-A directories.

The deliberate wrong-generation control is retained as a run-local script:

```sh
"/Users/lanceship/Documents/Codex/Digitect firmware research project/work/digikit/.venv/bin/python" out/runs/recorder-freeze-native-20261020-03/check-wrong-generation.py out/runs/NEW-NATIVE-WRONG-GENERATION
```

It clones the DSP state and deliberately redirects the snapshot to the latest
buffer. Different T6 PCM must result; it does not alter the positive baseline.
Its outcome is included in final `verification.json`.

## C: audited recommendation, no installed gesture

`recorder-freeze-gesture-20261020-01` traces untouched stock key 50 SAMPLING
and 43 C push. Holding SAMPLING and pressing/releasing C leaves SRC visible.
SAMPLING release then has flags `0x0`, suppressing its ordinary tap action.
FUNC+SAMPLING still opens the SAMPLES menu. Screenshots and raw flags/caller
PCs are retained. These results support **SAMPLING held + C push** in BUF mode
as the one recommended candidate. Broader page/context and physical debounce
behavior remain to be checked. No competing double-STOP, standard arm or
project shortcut is reassigned.

The user's brief explicitly requires selection before a binding is installed.
The current command remains diagnostic; no `B1-001 FROZEN` toast is claimed.
A future binding needs a native UI/worker bridge respecting audio deadlines;
the IPL-7 paused diagnostic must not be copied blindly into a performance ISR.

## Regression, failures retained, and remaining blockers

**302 source/native tests pass** in
`out/recorder-freeze-native-unittest-20261020-01.log`. SINE replay passes in
`out/runs/20261020T134140Z-test-8377764b/manifest.json`. Plaits, Capicola, old
recorder/Flex source and fixture expectations remain byte-identical to the
560-source audit. No new Plaits/Capicola DSP algorithm or build recipe was used;
source regressions and SINE do not replace their hardware tests.

Failed/incomplete controls are preserved:

- Initial NORMAL `*-01` exploration reached the original filename/assign UI,
  then report serialization exposed the incompatible byte/sector overlay maps.
- NORMAL `*-02` are stereo smoke results, not full gate passes.
- NORMAL `*-03` failed on a second record because stock retains the accepted
  recorder candidate; the driver now explicitly discards it before recording
  again. The old expectation was not changed to conceal a firmware failure.
- `recorder-normal-after-buffer-20261020-01` shows the real reserved-slot LOAD
  ERROR; the native first-free filter fixed it, followed by a successful repeat.
- `recorder-freeze-native-20261020-01` failed its required B1-001 name assertion;
  stock cache aliases preserve their original name. The native command now
  publishes the snapshot name explicitly. `-02` passes the earlier bounded
  native proof; `-03` adds cache-miss/incomplete-publication controls.
- The first unit reference-corruption driver moved its ID outside the owned
  namespace and observed the intentional stock fallback. The corrected test
  corrupts it to another owned, unissued ID and still requires native rejection;
  a separate file-namespace fallback check remains.

After the executable runs, one unused import was removed from the standalone
gesture tracer for lint. Native emitters/adapters, NORMAL driver, audio oracle,
tests and all existing sources are unchanged from their passing runs. Final
verification records both manifests and this auxiliary-only cleanup; it does
not relabel a source-drifted run as passing.

Still host-assisted: recorder/WAV producer, BUF candidate/commit transaction,
diagnostic invocation, sector/DMA models and separate page/audio replay.
Native registration follows the host BUF commit; that larger transaction's
failure/rollback boundary is not made native by this work. No complete project,
pattern, queued-trigger, lock, undo/clipboard or active-reader lifetime closure.
No native DSP readback, SAVE for DSP-only audio, target workspace placement,
coupled deadline measurement, reboot durability or hardware installation.

This is a **stock-image emulator adapter**, not an all-features integration.
Its original-resource byte guards intentionally refuse already-patched entry
points. The generation range also overlaps legacy Flex's temporary ID range;
the two registries must not be activated together without an explicit shared
dispatcher/ownership design. Preserving the old implementation and its outputs
does not establish their simultaneous coexistence with this new adapter.
Internal registration assumes valid slots from the completed host buffer
loader; arbitrary corrupted pointers/project teardown are outside this proof.

The most useful next engineering increment is a **native buffer publication and
registration worker transaction** with explicit completion/failure ownership.
That removes the remaining host commit boundary and establishes where an
approved performance gesture can safely enqueue work. Reader retirement and
native readback remain separate necessary stages for indefinite reuse and
optional +Drive saving. Legacy Flex stays intact until replacement parity.
