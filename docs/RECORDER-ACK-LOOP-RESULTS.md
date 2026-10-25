# Recorder acknowledgement in the running control path

2026-10-22 continuation: the isolated conditional-MODIFY repair and corrected
replacement/FREEZE matrix now pass twice. See
[the runtime/matrix results](SHARC-CONDITIONAL-MODIFY-RESULTS.md). The text
below retains the original blocked-stage findings and failed runs.

Digitakt II OS 1.16, 2026-10-21. Opt-in emulator experiment; no device build.
Continuation of [the diagnostic echo](RECORDER-ACK-RESULTS.md), with the
[frozen implementation proposal](RECORDER-ACK-LOOP-PROPOSAL.md).

The native acknowledgement integration and focused checks pass. The full
playing/re-recording matrix is blocked by an unsupported stock DSP instruction
in the pinned emulator. Two coupled runs stop at the same instruction; an
independent stock-only control reproduces it. Replacement, recovery under
transport faults and the final NORMAL round trip are **not passed** by this
experiment. Memory/identity reuse remains disabled.

## Implemented path

The new `lab/recorder_ack_loop.py` composes with the existing queued BUF/FREEZE
adapter. It preserves every inherited implementation source and normal builder.

1. The original queued BUF worker captures/loads/registers a new generation,
   frees its transient CPU source and flushes its completed logical header.
2. A native CF thunk derives epoch, generation and extent from that worker and
   the original allocator records. It calls the unchanged native echo sender.
3. The original CPU frame ISR calls DSPI2 at `0x4002dd74`. The original driver
   copies its previous receive staging and starts the next descriptor exchange.
4. At the ISR return `0x4002dd7a`, native code pops the original arguments,
   preserves live registers, calls the native matcher and resumes at
   `0x4002dd88`. No host pump or host receipt write participates.
5. The SHARC native DMA model raises sources 69/70. Original interrupt entry,
   IVT, SEC acknowledgement, SSL dispatch, completion callback and SEC END run.
   The harness does not enter SPI callback `0x1c77b4` or supply its event code.

The echo remains a receipt of a diagnostic tuple. It does not acknowledge PCM
DMA completion, reader retirement, ownership release or permission to reuse.
All eight recording generations/eight snapshot limits and pins remain intact.

The independent dispatch coverage probe records two visits to IVT `0x9003c`,
SEC-ID ACK `0x1c0b92`, callback `0x1c77b4` and SEC END `0x1c0be2`. The
callback's toggle body runs once, matching the one receive-ring transition.
Its blank-frame case executes 1,041 native instructions and drains both
sources. Raw coverage and the script are retained in the audit directory.

An independent startup/audio control uses the authenticated prior native A
and FREEZE pages, shared T1/T5 and frozen T6. Across 12 blocks, all 32 raw
voice buffers match the original prepared stock replay exactly, including
nonzero audio (peak `0.1221923828125` in block 1). This checks that the partial
startup/interrupt path did not make the paired comparison silently vacuous.
See `voice-startup-control.py`, its input hashes and per-block result JSON in
the audit. Its PCM pages are the preceding worker fixture, separate from the
new coupled recorder captures.

## Native dispatch setup and remaining models

The prepared pack has no enabled global interrupt path. The experiment enables
the pinned architectural bank/stack/peripheral models and executes these stock
startup segments, stopping at explicit safe boundaries:

| Segment | Native effect |
| --- | --- |
| `0x1c0f24..0x1c0fa5` | Stack/bank defaults, IVT location, interrupt mode and runtime initialization |
| `0x1c8173..0x1c817a` | Original call site for SEC initialization `0xb8cdaa` |
| `0x1c80a0..0x1c80a9` | Original call site for SPI2 initialization `0x1c7bd4(0xabc)` |
| `0x1c7756..0x1c775d` | Original audio-task block call, with pending interrupts serviced by the core |

The host supplies the missing SEC reset-bank fixture, schedules a block per
CPU exchange, and starts the original task call at a boundary with no active
interrupt. This is a bounded control-path test, not full DSP RTOS startup or a
concurrent timing model. CPU SSI/interrupt cadence, recorder service input,
LP0 delivery/callback entry and low-level storage remain emulator models.

The modeled startup leaves SEC CSTAT `0x10012`, including error flags. They
are retained, reported and required to remain unchanged during exchanges;
sources 69/70 must both drain to zero and IMASKP must clear. This closes the
functional dispatch path under this fixture, not clean reset/W1C behavior or
physical peripheral correctness. Dependencies are not patched to conceal it.

## Request construction and preemption control

The CF worker and frame ISR share a processor and may preempt one another.
The new thunk first disables the previous matcher. The unchanged request code
then constructs its tuple/table and marks PENDING last. Every guest write to
the five expected fields and 48 fragments is checked in the native unit test
to occur while matching is disabled, including a second request while the
first is pending. No long IPL-7 section is introduced.

An unguarded-source control fails with observed phase `1` where `0` is required;
the original unguarded source and exact failure are retained in
`recorder-ack-loop-audit-20261021-01/pending-guard-control.json`. The ISR unit
also verifies its original four-argument stack pop and live-register values.

## Address and resource boundaries

CF allocation metadata is indexed through `0x405b5368`, vector `0x405a0f64`,
52-byte records, start/size at `+0x10/+0x14`. These are logical DSP extents.
The actual DSP byte address is `0x8422b9c8 + logical_start - 0x400`. Slot
descriptors use the relative DSP offset; their left-channel data starts 32
bytes into the allocation. The frozen-data oracle checks that relationship
before hashing. No CPU pointer is dereferenced on SHARC.

New CF code uses a separate 16 KiB emulator mapping at `0x10a00000`, not a
hardware reservation. Existing diagnostic maps and packet staging are reused.
There is no new DSP kernel, PCM reservation, sample identity or file per echo.
Capicola's 8 MiB reservation is untouched. Hashes/readback of DSP RAM are host
diagnostics, not native SAVE. Project persistence remains guarded.

## Reproduction

Use the configured Python 3.12 interpreter from `.local/config.json`. Existing
authenticated private fixtures are required. Fresh output directories only:

```sh
LAB_PYTHON="$(python3 -c 'import json; print(json.load(open(".local/config.json"))["python"])')"
./labctl doctor
"$LAB_PYTHON" scripts/check-recorder-ack-loop.py out/runs/NEW-LOOP
"$LAB_PYTHON" -m unittest discover -s tests -v
./labctl test sine --replay
"$LAB_PYTHON" scripts/check-recorder-ack.py out/runs/NEW-OLD-ECHO
"$LAB_PYTHON" scripts/check-recorder-worker-publication.py \
  out/runs/recorder-freeze-queue-native-20261021-02 \
  out/runs/NEW-PUBLICATION --require-atomic
```

`LAB_PYTHON` above means the literal configured interpreter, not system Python.
The loop probe saves frozen sources, wire/receipt/publication traces, native
instruction observations and complete TX/RX streams. It compares all 32 voice
work buffers and every non-carrier wire byte against the original stock engine
after every exchange. These are voice taps, not final DAC output or listening.

Use `--smoke` for the bounded native completion/receipt check without shared
selection, FREEZE or replacement. The full command currently reproduces the
blocker below. The independent control can be rerun from the retained audit:

```sh
PYTHONPATH=. "$LAB_PYTHON" \
  out/runs/recorder-ack-loop-audit-20261021-01/type7a-stock-control.py
```

## Results and the blocking instruction

| Check | Observed result |
| --- | --- |
| Complete unit suite | 354 tests pass, including both new executed-CF ABI/preemption tests |
| SINE replay | Pass; `20261021T142525Z-test-0aacf3e2/manifest.json` |
| Existing echo regression | All 17 conditions pass; `recorder-ack-loop-original-20261021-01/report.json` |
| Existing atomic-publication regression | Pass with `--require-atomic`; `recorder-ack-loop-publication-20261021-01/report.json` |
| Native dispatch coverage | Stock IVT/SEC/SSL invokes SPI completion; disabled SEC fails closed |
| Current-source coupled smoke | Pass; 1,327 native exchanges/CPU ISR polls, one native worker request, receipt at 50 polls; `recorder-ack-loop-native-20261021-08/report.json` |
| Independent audible-voice startup control | All 32 voice buffers exact for 12 blocks with nonzero PCM |
| Coupled replacement exact repeat | Runs `-06` and `-07` both fail at stock short-word PC `0x1cbc93` before B capture/publication |
| Stock-only instruction control | Both Python semantics and native core reject the original EQ MODIFY with AZ clear or set; original unconditional MODIFY executes |

Unit log: `out/recorder-ack-loop-unittest-20261021-04.log` (18.122 s).
SINE log: `out/recorder-ack-loop-sine-20261021-04.log`. These checks use the
final implementation sources. The original regression's direct diagnostic
entry/polling remains an independent protocol regression; its fault results
do not close the new running-path matrix.

The current smoke records 7,488 stereo frames into a 32,768-byte DSP
allocation. Native CPU buddy free space rises from 28,066,112 to 28,098,880
bytes (32,768 reclaimed), and the generation node's CPU source pointer is
zero. The request originates from the native completion thunk, with no host
pump or receipt write. Its sources equal the frozen `-06`/`-07` sources
exactly. The smoke has no active musical reader; its 32-lane PCM comparison
alone does not establish audible playback or safe replacement.

Both full runs complete native A publication and receipt, manual selection
of BUF 1 on T5, queued FREEZE A, snapshot selection on T6, looping A and
sequencer start. The first SAMPLING tap to begin recording B then reaches:

```text
Native path 0x1c7756: 0x1cbc93,
native-trap: sharc_core.forms_dag._type_7a:63:
stop: unsupported Type7a predicate at 0x1cbc93
```

FREEZE's stimulus here is the existing test request serial followed by a
zero encoder turn to wake GUI polling. Native GUI polling queues the original
FREEZE worker; the host does not invoke that worker or write its registry
commit. This is not a validation of the proposed long-press shortcut.

The original OS 1.16 opcode bytes are `81 04 00 20 00 00` (loader order).
The decoder calls it `IF EQ modify(I4, M4)`; fields are Type7a, cond=0,
w=1, l=0, no compute. The pinned implementation admits only predicates
`0x1f` and `0x17`. It stops before consulting EQ, even when the condition is
false. Both full logs retain the actual DSP exception. Their outer reports
say `CPU failed: None` because the exception terminates the GUI worker thread;
that wrapper message is not a separate CPU failure diagnosis.

`type7a-stock-control.py/json` uses the unchanged stock BLOB and prepared
native core, with no recorder, echo overlay, transport or UI. Both AZ=0 and
AZ=1 reproduce the same stop, leave I4 unchanged and execute zero native
instructions at that PC. The adjacent original unconditional Type7a at
`0x1cbc74` executes in both engines, advances to `0x1cbc77` and yields
I0=`0x84230010` from I5=`0x84230000`, M5=4 under explicit NW32 scaling.
The control's first diagnostic drafts had an incorrect unscaled expected
address and then mismatched Python/native NW32 options; those failed logs
remain beside the corrected, explicitly matched fixture (`-04.log`). No
stock opcode or emulator semantic was changed to obtain this result.

This isolates an existing emulator support gap. It does not prove why the
complete firmware flow chooses this branch, that a physical device fails, or
that replacement would pass after the instruction is supported. The paired
engines match every completed block up to the stop, but the patched engine
runs first and aborts before its stock peer executes the failing block.
Both runs contain 13,595 completed/compared blocks; exchange 13,596 traps.
TX, RX, instruction-count and receipt files are byte-identical across the two
runs. This is an exact repeat of a failure, not a successful replacement run.

The delayed/drop/duplicate/stale/zero/recovery sequence, replacement while an
old voice remains active, late frozen-A playback and final NORMAL return all
remain unexecuted in this coupled experiment. The probe retains their exact
assertions and never writes a success matrix on this failure.

## Source identity

Branch `codex/plaits-macro-controls`, HEAD
`77b1c2a1746a355b66b1a7e1cb61939c9bc0fdb5`, plus preserved inherited dirty work.
DigiKit `277760aad51b036a4756db051409d4d3b1eeccbc`; Selache
`2b26d3b75c53063575bc5c820fa0d38879335187`. MAIN SHA-256
`57bb4dfa8df07d846adc72fdb4fb0d3cd3c5680c524bf498338460207e008e7d`;
original BLOB
`0f514a12a2255f5c081e292c47f1f29462003177658da4bbae0a22fd737fffa2`.
The constructed echo BLOB is unchanged from the previous echo experiment:
`6cd12c9191647fe1d71a1832e3715c5b72966dc7cf1ca0a6e7a8b828031189b6`.

Proposal SHA-256
`f264de9c4ad5c497d488e7b922df956a477b1721cf348185acbae8f4ea0b40bb`;
contract SHA-256
`9016fd286594c2c6cb50cb80dc3acae92ec9e04c2328d60b5406d976744cb0e4`.
Readiness was recorded before implementation. The audit directory is
`out/runs/recorder-ack-loop-audit-20261021-01/`.

All 592 inherited source/contract files and 56 inherited unit files retain
their original bytes. Three source/contract files and one unit file are added.
The 595-file frozen source manifest SHA-256 is
`601adb5d836ee0ade599f9f495ea9fcf0f21787318bdd5522029427dbd64d1c0`;
57-file unit manifest
`57e085a1d188143f846b0ef3afcf5f0b2bc70580eb0f213e22ad506527e1376e`.
Final source preservation, clean dependency checkouts, doctor and Ruff checks
pass. `verification-final.json` in the audit records the passed checks and
the blocked matrix separately; it is not an overall acceptance pass.

## Retained controls and repairs

- The disabled-SEC control leaves completion pending and the ring select
  unchanged. There is no manual callback fallback.
- The unguarded CF submit control fails before constructing a second tuple;
  its old pending phase is still visible. The guarded native unit covers all
  106 tuple/table writes across two submissions.
- Direct top-level calls with the architectural stack model enabled did not
  supply a valid C caller frame. The corrected preflight starts at original
  linked call sites. Missing SEC registers are explicit fixtures, not hidden
  defaults or dependency patches.
- Run `recorder-ack-loop-native-20261021-01 --smoke` passed 2,150 coupled
  exchanges and a native receipt at 50 polls. It had no active musical reader
  and is not counted as the replacement matrix.
- Runs `-02` and `-03` were deliberately interrupted before acceptance to add
  the preemption guard and correct the diagnostic's CPU/DSP origin conversion.
  Their original source snapshots and partial captures remain available.
- Runs `-04` and `-05` failed the active-reader setup. Large `B=-127` encoder
  bursts skipped the loop modes in the actual timed control stream (PLAY
  moved from `0x0300` through `0x00b2` to zero). They did not pass replacement.
  The corrected input uses small `B=-5` turns and checks the real DSP reader.
  `play-small-turns.py/json` records a loop at turn four with PLAY `0x0283`.
  Both failed full runs had already passed native USE, receipt, shared manual
  selection and queued FREEZE before this assertion.

No golden baseline was regenerated. Old controls, failures and interrupted
validation attempts remain in ignored output directories. The GUI capture
sink's old `render_stats()` counters still print zero; actual coupled DSP
execution is accounted by the probe's native completed-block/PCM reports.

## Next gate

The immediate next task is a separately isolated emulator change supporting
conditional Type7a MODIFY, preserving the pinned working runtime as a control.
First establish predicate, scaling, circular-wrap and optional-compute behavior
from the instruction specification; test EQ true/false, other predicates,
source/destination aliases and flags. Validate Python/native agreement and
stock replay before repeating the unchanged full recorder matrix. Do not
NOP the instruction, skip its branch or simulate the missing buffer commit.
No dependency update or such semantic change is included in this increment.

Keep memory and identity reuse disabled. The generation-specific queued-trigger
barrier and all logical/alias/snapshot/preview/lock/project/save-job roots must
be closed before any retirement permission. Full startup, composed carrier
ownership/write ordering, actual capture, native DSP readback/SAVE, real bar
arming and physical deadlines remain separate dependencies. No hardware was
flashed or uploaded; no commit, push or publication was made.
