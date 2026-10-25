# Native pending controls and recorder retirement diagnostics

Digitakt II OS 1.16, 2026-10-22. Opt-in emulator experiment; no device image.
[Frozen plan](RECORDER-RETIREMENT-GATE-PLAN.md),
[preceding runtime/matrix results](SHARC-CONDITIONAL-MODIFY-RESULTS.md).

The native diagnostics distinguish a pending sample selection from an active
reader and preserve that association when a descriptor is cleared. This closes
an observation gap; **it does not establish a complete retirement barrier**.
No backing allocation or sample identity is freed/reused. The existing
8-generation/8-snapshot limits remain unchanged.

All 16 focused conditions pass in two exact repeats. Both complete coupled
replacement/FREEZE matrices pass, including seven native recordings and the
inherited NORMAL-return assertions. All 358 unit tests, SINE replay, atomic
publication, 17 receipt-transport cases and 102 native instruction cases pass.
This is a validated emulator diagnostic prototype; native retirement/reuse is
still blocked, not implemented.

## Implementation and ownership

- `machines/recorder-retirement-gate/gate.c`: original native diagnostics.
- `lab/recorder_retirement_gate.py`: opt-in compiler/assembler/linker adapter,
  guarded hooks, context preservation and overlap checks. It composes with the
  unchanged observer and, separately, the unchanged receipt echo.
- `scripts/check-recorder-retirement-gate.py`: deterministic paired native
  playback and explicitly labeled ABI fixtures; no host commit or registration.
- `scripts/check-recorder-retirement-gate-matrix.py`: installs the overlay into
  the existing corrected native panel matrix. All original assertions, expected
  audio and approved T1-selection inputs remain unchanged.
- `machines/recorder-retirement-gate/contract.json`: generated constants,
  required cases, exact proposal hash, ownership unknowns and forbidden actions.

| Layer | Actual operation | Evidence boundary |
| --- | --- | --- |
| SHARC control | Observe entry at SW `0x1c2b24`; replay original six-byte stack instruction | Actual target instructions; prepared execution context |
| SHARC slot lookup | Observe stock `0x1c3f78` before it resolves `0x257810 + slot*20`; replay original prologue | Actual slot acquisitions counted; no forced assignment |
| SHARC post-block | Compose at `0x1c75c5`, after stock processing; preserve displaced I2/I3 reloads | Completion of an observed control pass, not global producer/queue closure |
| Root scan | Existing 32-lane reader scan plus descriptors and cached/incoming sample selections | Covers exercised stock ONESHOT representation; other machine caches unresolved |
| Native recorder/FREEZE | Existing queued ColdFire worker and stock loader/alias path | Coupled matrix executes these instructions; capture source and LP0 entry remain modeled |
| CPU return | Existing generation/epoch/sequence receipt echo | Receipt only; these new diagnostic results are not a native retirement acknowledgement |
| Authoritative PCM | Existing stock DSP allocations and frozen aliases | CPU transient PCM reclamation is preserved; DSP backing remains pinned |

The new overlay emits 8,286 code bytes and maps 16 KiB of explicit emulator
scratch at `0x200fc000..0x200fffff`; code is at `0x200d0000..0x200d7fff`.
This is not a proven free hardware region. Loader overlap checks preserve the
inherited observer/echo regions. No sample-pool reservation is added, and
Capicola's existing 8 MiB is untouched.

The stock parameter cache is `0x2558dc`; incoming banks are `0x264220` and
`0x265220`. For each of 16 tracks, selection is at frame `+0xe0 + track*0x60`.
Diagnostics classify matching selections conservatively even with no trigger.
They are references that might be consumed, not a count of audible notes.
Cached event bits at `+0x22/24/26/28/2a` are reported separately.

On a new validated request revision, the native code builds a 1,025-bit union
of descriptor slots observed to overlap the immutable generation extent.
It keeps this union for that request so a later header clear cannot erase a
known pending slot association. This is not a complete historical registry:
references removed before the request and future producer admission are still
unresolved. A new request requires matching tuple/revision and a fresh native
control pass; old committed results must not be consumed as current results.

DSP reason bits: `1` active pointer, `2` inactive retained pointer, `4` live
descriptor, `8` cached/incoming selection, `16` no matching completed control
pass, `32` invalid extent, `64` stale/uncommitted inherited observation,
`128` exhausted serial. Descriptor counts distinguish logical BUF 300–303,
private 304–311, snapshots 312–319, preview 1024, and other aliases.
A private descriptor is still allocation ownership; this code never treats it
as permission to free its backing.

Status `1` is RETAIN. Status `2` is DSP_CLEAR_OBSERVED for the inspected
representations after a matching native control pass. It is demonstrated only
with a deliberately rootless ABI fixture. **Permission remains zero**, including
in that fixture. Separate unknown-ownership bits stay `0x7f`:

| Bit | Missing proof |
| --- | --- |
| 1 | ColdFire allocator/cache aliases |
| 2 | Project, pattern, locks, undo and clipboard roots |
| 4 | CPU preview and save-job leases |
| 8 | Admission seal and all future/queued control producers |
| 16 | Actual DMA/cache completion |
| 32 | Other playback-machine reader state |
| 64 | Native delivery of a retirement result and atomic lease closure |

The native code cannot free memory and no host observation clears these bits.
The direct-call negative covers an observer invocation without prior control
entry; it is not arbitrary mid-function preemption or an admission-seal proof.
The aliased snapshot and private-owner lifetimes remain the preceding worker's
responsibility. Sample-lock and actual project-transition lifetime closure are
not inferred from a protocol epoch change or a synthetic descriptor fixture.

## Focused observations

Each final focused repeat passed all 16 cases over 2,829 paired blocks,
comparing all 32 voice work buffers and both stock reply banks exactly.

| Boundary | Observed result |
| --- | --- |
| A active, shared T1/T5 plus frozen T6 | Reader mask `0x0f03`; one logical, one private, one snapshot descriptor |
| B trigger block | B reader mask zero; cached and incoming selection mask `0x0011` (T1/T5), event mask `0x0031`; RETAIN |
| Following block | B reader mask `0x0303`; four native matching slot lookups, last slot 300, control serial 26 |
| A after B replacement | No logical A root; private owner and snapshot still present |
| A naturally ends, then frozen T6 is triggered later | A reacquired with reader mask `0x0c00`; exact stock PCM |
| Direct observer call on rootless ABI fixture | No completed native control pass; reason `16`, RETAIN |
| Rootless ABI fixture after real control/block path | DSP_CLEAR_OBSERVED, unknown ownership `127`, permission `0` |
| Inactive pointer, preview/other alias, invalid descriptor | Each produces its corresponding retaining reason |
| Higher project epoch | Cannot inherit prior completion; stale earlier epoch rejected |
| Saturated control serial | No wrap; retaining reason `128` remains set |

The zero-reader comparator would approve the B trigger block. Native diagnostics
reject it using the pending selection association. An independent destructive
control clears B's logical and private descriptors via the original LP0 header
handler before consumption, without freeing PCM. The pending association still
appears (`0x0011`) while current descriptor counts are zero. The following block
loses B: T1's sample pointer becomes zero and PCM differs from the unchanged
stock engine. This is a repeatable lost-trigger control, not an acceptable drain
strategy. The earlier allocator-reuse corruption control remains unchanged.

ABI fixtures explicitly write DSP state to test classification/refusal. They
are not actual project changes, native CPU root enumeration, sample-lock UI
coverage, or a successful root-draining implementation. The ordinary paired
replacement uses captured native worker pages, not a host-created commit.

## Performance and limits

The fixed frame work includes the inherited 32-lane/1,025-descriptor scan and
one added 1,025-descriptor scan, 48 selection checks, and a small fixed alias
bitmap. Getter-hook frequency follows the stock workload. Each final focused
run adds 751–108,000 emulated retired instructions per block relative to stock,
mean 104,888.06, including inherited observation overhead. This is diagnostic
work, not a shipping audio-deadline budget or physical DSP utilization.

Capture production, LP0 transport/callback entry, CPU/DSP cadence and partial
startup remain modeled. The coupled experiment retains the SEC startup error
flags. Full RTOS boot, actual interrupt preemption, composed carrier write
ordering, physical DMA/cache behavior, final DAC output and listening remain
unverified. Native DSP readback/SAVE and real sequencer next-bar arming remain
separate dependencies. No additional playback-machine compatibility is claimed.

## Complete source-frozen validation

| Check | Observable result |
| --- | --- |
| Focused probe `recorder-barrier-probe-20261022-02` / `-03` | Both pass all 16 conditions; checks, trace, instruction counts and compiled image match exactly |
| Coupled `recorder-barrier-matrix-20261022-01` / `-02` | Both pass all 15 inherited conditions, with 20,451 exchanges/control passes and seven native recordings each |
| Shared playback/replacement | Old A remains active during B publication; subsequent T1/T5 triggers use B; T6 uses frozen A |
| Stable identities | T1/T5 remain on logical slot 300; frozen T6 remains on 312; no recycling |
| Receipt faults | Polls: normal 50, delayed 54, dropped 98, duplicate 98, stale 192 timeout, zero 192 timeout, recovery 50 |
| CPU source reclamation | All seven source pointers zero; 131,072 bytes of transient allocator blocks reclaimed cumulatively, not an instantaneous whole-device free-space increase |
| DSP allocation policy | Seven allocations remain pinned, totaling 128 KiB in this short-sample matrix; FREEZE aliases A without another PCM allocation |
| New diagnostics in actual worker flow | 20,451 native observations/control serials each; no permission, no rootless status, unknown ownership always retained |
| Frozen A | Whole allocation hash unchanged; late trigger at exchange 18,958 still obtains A |
| Full unit suite | 358 passed, 22.379 seconds; all 59 inherited unit files unchanged |
| SINE replay | Passed, `20261021T215230Z-test-a9f4562a/manifest.json` |
| Existing atomic publication | Passed with `--require-atomic`, old-reader preservation and complete-header checks |
| Existing receipt protocol | All 17 cases pass, including reorder/corrupt/supersede in its focused transport test |
| Isolated runtime instruction checks | 102 native/Python cases plus actual stock conditional MODIFY pass |
| Final integrity | Doctor, Ruff, diff check and frozen-source checks pass; dependencies clean |

Nine complete matrix artifacts match exactly between runs: `tx.bin`, `rx.bin`,
`instruction-counts.json`, `receipts.json`, `publications.json`,
`publication-readers.json`, `wire-trace.json`, `stimulus.json`, and
`retirement-gate.json`. All seven non-instruction/diagnostic artifacts also match
byte-for-byte against the preceding accepted conditional-MODIFY matrix. No
baseline or assertion changed. PCM stream hash for all 32 voice work buffers:
`be1bfad060985fe062d782276c813ecab75deb101259edc7fa73bdc1602e399b`.
Frozen whole-allocation hash:
`01f73740cea10b383bde36393d65542079ae9c35509e42bba897de8565db28b9`.

The added diagnostics cost 414–58,278 extra retired instructions per coupled
block compared with the preceding observer/echo matrix, mean 49,893.29. Maximum
whole-block native instruction count is 380,070. These are emulator instruction
observations, not physical cycles, latency, utilization or deadline guarantees.
GUI summaries reporting zero SHARC audio frames refer to its disabled optional
live-audio helper; the independently executed native peer records and compares
20,451 SHARC blocks. No real-time or listening claim follows.

The final aggregate is
`out/runs/recorder-barrier-audit-20261022-01/verification-final.json`;
`verify-final.py` reproduces the checks. All 604 inherited implementation/contract
files and 59 inherited unit files preserve their exact initial bytes. Five new
implementation/test-driver files make the frozen source map 609 files. The only
addition to the preceding results document is a link to this continuation.

Final proposal SHA-256:
`d665b441e7c44829b74d2563f16981eb13a3ba899e3db4cb9fd9645c90fa1681`;
contract `5c2f83814f64027986c7eace1a46f41c3e7038c80e4bb07c121a042ac6f81ccb`;
frozen source map
`acf2704319b0ca630ca3e5354104bae962b97017e0869af9d544e5a2fc5dd669`;
unit map `9b638a929c4fe1c5a75d00863cda005f299e1014aae4bd388323e57ff10341fa`.
Compiled diagnostic image:
`d4e9a786dc74fb26b174f5f591a2b1de6e68af202778c870f09eb65bf555b153`;
composed coupled DSP image:
`fc939ca329363cfd4462caf293dcdd5811cbc3e03cb50aae54a38cd88b05ade3`.
Original stock snapshot, card, MAIN and LP0 inputs also retain their literal
expected hashes; `stock-inputs-after.json` records the final check.

## Required next boundary

Do not free an allocation from this report. The next implementation needs a
extension of the existing native generation registry with ownership leases and
an admission seal on the ColdFire side,
linked to an explicit ordered control watermark that SHARC consumes. It must
account for allocator aliases and every producer/root, preserve already queued
notes, retain frozen generations, and deliver a matching completion result back
to the CPU before the original private-slot release is allowed. Unknown roots
must retain storage. The existing receipt cannot be reinterpreted as that result.

First prove this for one unfrozen generation with no remaining roots. Only then
release one allocation through the stock allocator while retaining the current
identity limits. A hundreds-recording memory-plateau test additionally requires
a proven bounded generation/identity lifetime protocol; freeing PCM alone does
not remove the eight-issued-generation ceiling. Do not raise that ceiling or
recycle identities to manufacture such a result. No firmware was flashed/uploaded, committed, pushed or published.

## Concrete CPU integration points, still unimplemented

EVIDENCE from the current source: `recorder_freeze_code.py` already has an
native generation registry with 64-byte records at CPU `0x10401000` and an
eight-entry snapshot registry at `0x10401800`. The current BUF worker admits
eight recording generations; the inherited lookup namespace spans 32 identities,
which does not authorize more private allocations or identity reuse. These
registry addresses are existing emulator mappings, not hardware reservations. Lookup `0x10403000` checks status, immutable
identity and current project epoch. The stock allocation vector is
`0x405a0f64`, record stride `0x34`; slot-to-block indices are at `0x405b5368`.
These are CPU metadata, not SHARC pointers or additional retained CPU PCM.

The existing queued worker serializes recorder/FREEZE mutation; the operation
wrappers in `recorder_freeze_worker_code.py` count original load/unload/clear
operations at their shared `STATE+56`. This is not a count of pending audio
triggers or all project roots. The existing slot guards protect reservations
and worker access; they do not seal every future lookup of an old generation.

INFERENCE for the next bounded increment: add a per-generation sealing/lease
state to this existing registry rather than create a parallel host registry.
Reject new old-generation acquisitions, retain current logical/frozen roots,
prove in-flight loader/preview/control work has drained, then send an ordered
native consumer fence. Test that pending notes still complete correctly.
The slot's own private allocation-owner reference must be distinguished from
playback/project roots before the final stock unload. Merely changing the
registry status or observing an operation count of zero is insufficient.
No such seal, fence, ownership release or new state transition is implemented
by this diagnostic overlay.

## Reproduction and provenance

Checkout: `codex/plaits-macro-controls` at
`77b1c2a1746a355b66b1a7e1cb61939c9bc0fdb5`, with inherited dirty work preserved.
DigiKit remains `277760aad51b036a4756db051409d4d3b1eeccbc`; Selache remains
`2b26d3b75c53063575bc5c820fa0d38879335187`. The isolated conditional-MODIFY
runtime is the preceding accepted build `sharc-type7a-build-20261022-02`.
Its library SHA-256 is
`9d2374a3fd6f4123e6cd2356f4e2c110b022282ddb8e0b788636be08b285c24d`, core
`748c18ea71c13e5860a1d7fc82699dc5e4b1f0f948008e5ffd83352c1bdb2bca`,
patch `c616746ba28ccda7739a586fa4dc628903ae951382b77db8b9d1beefb2e4fc57`.
The runtime wrapper validates all three and the copied source tree before any
SHARC import. Audit `selected-runtime.json` additionally records the actual
loaded library observed with `lsof` in both repeat and both matrix processes.
Doctor's original fixture-library hash describes a baseline input, not the
selected execution engine. No stale-library option or host fallback is enabled.

Use fresh output names under ignored `out/runs`. From the repository root:

```sh
LAB_PYTHON="$(python3 -c 'import json; print(json.load(open(".local/config.json"))["python"])')"
./labctl doctor
# Rebuild the isolated runtime first if the preceding accepted build is absent:
# "$LAB_PYTHON" scripts/build-type7a-runtime.py out/runs/NEW-TYPE7A-BUILD
"$LAB_PYTHON" scripts/with-type7a-runtime.py out/runs/sharc-type7a-build-20261022-02 -- \
  scripts/check-recorder-retirement-gate.py out/runs/NEW-GATE-01
"$LAB_PYTHON" scripts/with-type7a-runtime.py out/runs/sharc-type7a-build-20261022-02 -- \
  scripts/check-recorder-retirement-gate.py out/runs/NEW-GATE-02
"$LAB_PYTHON" scripts/with-type7a-runtime.py out/runs/sharc-type7a-build-20261022-02 -- \
  scripts/check-recorder-retirement-gate-matrix.py out/runs/NEW-MATRIX-01
"$LAB_PYTHON" scripts/with-type7a-runtime.py out/runs/sharc-type7a-build-20261022-02 -- \
  scripts/check-recorder-retirement-gate-matrix.py out/runs/NEW-MATRIX-02
"$LAB_PYTHON" scripts/with-type7a-runtime.py out/runs/sharc-type7a-build-20261022-02 -- \
  scripts/check-recorder-worker-publication.py \
  out/runs/recorder-freeze-queue-native-20261021-02 out/runs/NEW-PUBLICATION --require-atomic
"$LAB_PYTHON" scripts/with-type7a-runtime.py out/runs/sharc-type7a-build-20261022-02 -- \
  scripts/check-recorder-ack.py out/runs/NEW-ECHO
"$LAB_PYTHON" scripts/with-type7a-runtime.py out/runs/sharc-type7a-build-20261022-02 -- \
  scripts/check-type7a-runtime.py out/runs/NEW-OPCODE
"$LAB_PYTHON" -m unittest discover -s tests -v
./labctl test sine --replay
"$LAB_PYTHON" -m ruff check lab/recorder_retirement_gate.py \
  scripts/check-recorder-retirement-gate.py scripts/check-recorder-retirement-gate-matrix.py
```

The focused input is the authenticated native queued-worker run
`recorder-freeze-queue-native-20261021-02`, whose report and page hashes are
checked literally before execution. Recreating that prerequisite uses the
preceding worker reproduction instructions; the test refuses substitute pages.
The coupled matrix instead performs new native recording and FREEZE jobs.
FREEZE uses the existing test mailbox plus native GUI polling/worker submission;
this is not a long-press shortcut test. The inherited NORMAL-return assertions
do not constitute a full new stock-save/reload run. Its screenshot filename
`normal-name-dialog.png` is not proof that the filename editor was reached;
the preceding focused NORMAL save/reload evidence remains separate.

Audit: `out/runs/recorder-barrier-audit-20261022-01/`. It retains before/frozen
source/test maps, the frozen plan/contract, initial Git status, static disassembly,
runtime identity, and the final aggregate verifier. Each executable run stores
its executed source snapshot, compiled assembly/listing, guarded patch records,
comparison history, exact diagnostic state and instruction counts.

Retained attempts and controls:

- `recorder-barrier-build-20261022-01` refuses the displaced instruction when
  the assembly omitted `(NW)`. Adding the explicit addressing-space suffix
  reproduces the original six bytes; build `-02` passes. No original opcode
  was changed to work around this check.
- The first exploratory header clear used the wrong rate/length field order;
  its trace is retained as `trace-queue.py/json` in the audit and excluded from
  the result. Corrected `trace-queue-02.py/json` proves zero-length descriptors.
  The executable negative control now asserts zero length before proceeding.
- Focused probe `-01` precedes import cleanup and clearer contract wording;
  it passed, but the final exact repeat is the separately source-frozen pair
  `recorder-barrier-probe-20261022-02` and `-03`.
- Destructive descriptor-clear and the zero-reader comparator remain failed
  safety strategies. Their failure is required for the diagnostic test to pass.
- No inherited expectation or assertion was regenerated or weakened.
