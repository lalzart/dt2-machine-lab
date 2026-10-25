# Conditional MODIFY and recorder replacement/FREEZE

Digitakt II OS 1.16, 2026-10-22. Local, opt-in emulator experiment.
[Frozen implementation plan](SHARC-CONDITIONAL-MODIFY-PLAN.md) and
[previous blocker](RECORDER-ACK-LOOP-RESULTS.md).

The isolated SISD conditional Type7a implementation and corrected coupled
replacement/FREEZE matrix pass twice, with exact repeated captures. Seven
recordings, old-reader preservation, shared playback, frozen-A preservation,
transport faults/recovery and the original NORMAL-return assertions pass.
Two earlier unchanged runs exposed a test-stimulus error; they remain failures
and are explained below. No original assertion or audio expectation changed.
No memory or identity reuse is enabled.

Follow-on: [native pending-control and retirement diagnostics](RECORDER-RETIREMENT-GATE-RESULTS.md)
now pass focused and complete coupled repeats. They expose pending selections
and explicit retaining roots, but do not establish a full retirement barrier
or enable backing/identity reuse. The preceding results below are unchanged.

## Implemented runtime

`patches/sharc-type7a-sisd.patch` extends the pinned GPL-2.0 DigiKit source
in a copied tree. The original LICENSE accompanies that tree. Only copied
`tools/sharc_core/forms_dag.py` changes. All pinned files, private fixture
libraries, normal firmware builders and inherited recorder code remain intact.

For newly supported concrete SISD predicates, false advances without evaluating
the DAG operands or compute. True performs the existing scaled/circular update
and optional compute from the original operand snapshot. Circular arithmetic
sign-extends the 32-bit modifier before scaling. Unknown conditions/mode,
unsupported new SIMD cases, invalid compute and unsupported wrap inputs stop.
The old unconditional/NOT-SV paths retain their previous behavior, including
their existing limitations. This is not a complete SIMD/ILAD/timing repair.

The semantics follow the [Analog Devices SHARC+ Core Programming Reference,
rev 1.5](https://www.analog.com/media/en/dsp-documentation/processor-manuals/SC58x-2158x-prm.pdf#page=349),
sections 14-46 through 14-48 and 6-10; no firmware instruction is replaced.

`lab/type7a_runtime.py` validates the plan/pins, copies the licensed tools,
native crates and tests, applies the guarded patch and builds offline. Strict
generation translates all 309 functions. `scripts/with-type7a-runtime.py`
selects the copied Python tooling and matching native library in a fresh
process. Source/core/library fingerprints are checked; no stale-library
exception, HybridEngine fallback or host instruction emulation is enabled.

## Instruction and compatibility gates

| Gate | Result |
| --- | --- |
| Independent expected Python instruction states | 102 cases pass |
| Native instruction states | Same 102 cases pass, including all supplied DAG registers, compute values, flags and progress |
| Original actual opcode at SW `0x1cbc93` | Isolated native core executes one instruction; AZ=0 keeps I4, AZ=1 advances I4 by 16 bytes |
| Baseline failed control | Original runtime still rejects that actual opcode with both flag values, executing zero instructions |
| Old unconditional/NOT-SV controls | Previous state and stop behavior preserved |
| Strict native generation | 309 functions translated, zero untranslated |
| Relevant copied upstream tests | 50 passed, 2 skipped, 6 subtests passed |
| Full lab unit suite after stimulus correction | 358 passed (354 inherited plus 4 new tests) |
| Baseline SINE replay | Pass |
| Isolated SINE suite | Pass, including stock isolation, clone parity, lifecycle and negative comparator |
| Existing atomic-publication test on isolated runtime | Pass with `--require-atomic`; old active pointers and complete header preserved |
| Existing echo regression on isolated runtime | All 17 checks pass, with capture hashes identical to the prior baseline run |
| Focused NORMAL after native BUF setup | Pass: monitoring, trim/name edit, cancellation, native save, independent stock PCM reload, selector restore and failed-open rollback |

## Original matrix and corrected panel stimulus

Runs `recorder-type7a-matrix-20261022-01` and `-02` both pass the former
unsupported-instruction boundary and all seven native recording/receipt
checks. Their poll counts are A=50, delayed B=54, dropped=98, duplicate=98,
stale=192 (timeout), zero=192 (timeout), recovery=50. They also pass active-old-A
at B publication, subsequent T1/T5 B pointers, frozen T6 A pointer, unchanged
frozen descriptor and unchanged whole-A-allocation hash.

They then fail `Shared logical references changed`. The test auditions T6,
which selects it, before accepting further recordings. Existing native USE
correctly assigns the accepted recording to that selected compatible track.
Observed zero-based native recording targets are `[0,4,5,5,5,5,5]`; final
wire slots for T1/T5/T6 are `[300,300,300]`. This is a changed track selection,
not mutation of frozen sample 312. Its descriptor and PCM hash had already
passed their checks immediately before that assertion.

The native USE entry obtains its track through stock getter `0x4004abe8`,
latches it at worker `STATE+16`, and revalidates it in the existing assignment
primitive. The source and reports support the expected autoassignment
convention. Neither the recorder backend nor the sample-slot resolver needs
to change to keep the frozen sample assigned on T6.

The correction is isolated in `lab/type7a_matrix.py` and
`scripts/check-recorder-type7a-matrix.py`: before opening SAMPLING with a BUF
destination, issue original panel chord TRK+TRIG 1. NORMAL destination input
is untouched. The original matrix script is fingerprint-guarded and executed
unchanged; no assertion, expected slot or audio baseline is replaced. A new
additional check requires all seven native recording targets to be T1. The
driver writes its panel events and target validation to `stimulus.json`.
There is no host track write, recording commit, publication or registration.

`machines/sharc-type7a/corrected-matrix.json` records this input amendment;
the original plan/proposal fingerprint remains unchanged. Both original
failures and their streams remain available. The audit's
`unmodified-matrix-failure.json` records the observed target/slot evidence.
The final normal return/late snapshot checks were not reached by those
unmodified runs and are not reported as passes.

## Completed corrected matrix

`recorder-type7a-matrix-20261022-03` and `-04` both pass all 15 registered
conditions, the added native T1 target check and the unchanged original
assertions. Each executes 20,451 original-task/SPI exchanges and 20,451 native
CPU frame-ISR matcher polls, with seven native worker submissions. No host
receipt pump, direct worker call or host BUF/FREEZE commit participates.
The echo DSP BLOB remains byte-identical to the prior experiment.

| Generation | Stereo frames | DSP allocation | Receipt polls | Result |
| --- | ---: | ---: | ---: | --- |
| A / 1 | 7,488 | 32,768 B | 50 | Receipt |
| B / 2 | 3,136 | 16,384 B | 54 | Delayed receipt |
| 3 | 3,152 | 16,384 B | 98 | Dropped-fragment recovery |
| 4 | 3,120 | 16,384 B | 98 | Duplicate-fragment recovery |
| 5 | 3,120 | 16,384 B | 192 | Stale reply times out |
| 6 | 3,136 | 16,384 B | 192 | Zero reply times out |
| 7 | 3,120 | 16,384 B | 50 | Fresh-request recovery |

The logical buffer remains slot 300 through all seven generations. T1/T5
finish on 300; T6 finishes on frozen slot 312. The first reader remains active
on A at B publication, subsequent shared readers resolve B, and a late T6
trigger at exchange 18,958 resolves A with an active reader. The frozen
descriptor and whole original allocation hash remain unchanged:
`01f73740cea10b383bde36393d65542079ae9c35509e42bba897de8565db28b9`.

Seven CPU generation nodes have source pointer zero. Native buddy frees reclaim
32 KiB once and 16 KiB six times: **128 KiB cumulative CPU PCM allocation**.
The six later source allocations reuse the same freed CPU address, rather
than retain another source per generation. This is reclaimed allocation across
the timeline, not a 128 KiB instantaneous free-space increase: native metadata
and UI allocations remain. DSP generation storage totals **128 KiB**, including
the pinned original A backing shared by FREEZE; no separate snapshot PCM copy
is added. Seven recording generations and one snapshot are issued. The existing
eight-generation/eight-snapshot admission bounds and all pins remain intact.

All 32 voice work buffers and all non-carrier reply bytes equal the paired
original stock engine after every completed block. TX, RX, instruction-count,
receipt, publication, publication-reader, wire-fault and stimulus files are
byte-identical across both corrected runs. The streamed voice-buffer hash is
`be1bfad060985fe062d782276c813ecab75deb101259edc7fa73bdc1602e399b`.
This is voice PCM evidence, not final mix/DAC output, listening or hardware.

The combined observer/echo overlay costs a measured mean 47,979.03 extra
emulated target instructions per task block over the stock peer in this
timeline (min 656, max 52,041; median 51,515). This includes the inherited
observer/echo work, not just the conditional-instruction repair. No target
instruction was added to the firmware for this runtime repair. These counts
are not DSP cycles, physical CPU load, latency or deadline headroom.

The NORMAL-return assertions pass without a BUF request. The immediate
`normal-name-dialog.png` capture still shows the stock trim screen with
`PLEASE WAIT`; it does **not** prove the filename editor has appeared. The
separate existing NORMAL persistence probe is run below to distinguish those
checks. None of this is native saving of DSP-only BUF PCM.

The focused `recorder-type7a-normal-20261022-01` probe passes with
`--prebuffer --queued-freeze`: original MON changes 0→1; the original trim
controls move; native naming/cancel/save and assignment run; an independent
stock loader reads exactly the expected trimmed stereo PCM. A forced file-open
failure preserves the prior track and emulated storage. Standard NORMAL does
not enter BUF USE. Its `04-edited-stock-name.png` actually shows the native
filename editor, unlike the coupled test's early busy screenshot. Original
file APIs execute; recorder input and low-level card sectors remain modeled.
The save uses a fresh NORMAL capture, not DSP-to-CPU readback of a BUF.

The instruction matrix includes EQ/NE, AC/AV/MV/SV/SZ/BTF, both DAG banks,
distinct destination/source aliases, signed modifiers, plain/SW/NW scaling,
normal-word space, forward/backward/exact-length wrap with CBUFEN off,
pre-compute condition flags and skipped invalid operands. Unknown mode/flags,
new conditional SIMD, oversized wrap, unknown length and invalid compute are
negative controls. The 64 arithmetic cases use seed 0 and independent expected
address calculations. These are bounded instruction tests, not a hardware ISA
conformance suite.

The upstream skips are an absent drive3 capture and program database in the
isolated source copy. The copied native compute corpus and deterministic
translation tests do run. The private lab SINE fixture is separately present.
Baseline and isolated `sine-440.f32` SHA-256 both equal
`2a38b64c83b1636b9f1a3793f6e78c71275d0a64ca2473c2e6b20bc183673eae`.

## Retained failures and diagnostic limits

- Build `sharc-type7a-build-20261022-01` compiled before the backward-wrap
  control exposed unsigned M-register handling. The second build corrects
  signed arithmetic only for the newly supported predicates. The failed
  backward-wrap assertion is reproduced by the retained
  `backward-wrap-negative.py/json` against that first copy; the first build
  is retained as a falsifying source/library artifact.
- Focused native attempts `-01` through `-03` stopped on assertions about
  diagnostic text. The pinned generator renders formatted wrap/compute
  errors as generic native traps, and a compute error names its original
  helper rather than the caller. The final test requires the exact expected
  unchanged state/progress, actual failure and correct original trap site;
  static diagnostic strings are still checked. Dynamic text is a documented
  generator limitation, not repaired or silently treated as success.
- Python/native agreement alone shares source semantics. Independent expected
  register states, the actual original opcode, baseline failures and exact
  pre-existing audio expectations provide separate falsifiers.

## Provenance and reproduction

Branch `codex/plaits-macro-controls`, HEAD
`77b1c2a1746a355b66b1a7e1cb61939c9bc0fdb5`, plus preserved inherited dirty work.
DigiKit pin `277760aad51b036a4756db051409d4d3b1eeccbc`; Selache pin
`2b26d3b75c53063575bc5c820fa0d38879335187`.

Accepted isolated build: `out/runs/sharc-type7a-build-20261022-02/build.json`.
Its native library SHA-256 is
`9d2374a3fd6f4123e6cd2356f4e2c110b022282ddb8e0b788636be08b285c24d`;
generated core fingerprint
`748c18ea71c13e5860a1d7fc82699dc5e4b1f0f948008e5ffd83352c1bdb2bca`;
patch SHA-256
`c616746ba28ccda7739a586fa4dc628903ae951382b77db8b9d1beefb2e4fc57`.
The original fixture library remains
`7368cec8498fd706f31732e17dcc1b78b893c72bd06e416a8ee064de9832f11f`.

The audit is `out/runs/recorder-type7a-audit-20261022-01/`. It retains readiness,
all 595 inherited source fingerprints and 57 inherited unit fingerprints,
the frozen patch and final source/test maps. Frozen source manifest SHA-256:
`0f449a7a14283836dd9f7eada7f506bc8f65d69248d6b6ff58634202f7ad13ec`;
initial unit manifest:
`f8680b102e263ec5d6696ebd389b22fe632d81125c87a1a5b3bf1e57dc2f386f`.
After the stimulus correction, the 604-file source manifest is
`f3f1fd16fd901f0d53a97f28a9fb22a4fa93d682045eb5b661da69a26c6d6923`;
59-file unit manifest
`9b638a929c4fe1c5a75d00863cda005f299e1014aae4bd388323e57ff10341fa`.
All 595 inherited source/contract files and 57 inherited unit files retain
their exact original bytes. The audit's `verification-final.json` records
the two passes, exact-repeat hashes and failed original-stimulus controls
separately. Doctor and Ruff pass; pinned dependency checkouts stay clean.
The patch lives outside the lab's general source-map directories; its separate
fingerprint is mandatory in the build and runtime-selection records.

Use the Python interpreter configured in `.local/config.json`, not system
Python. From the repository root, choose fresh output names:

```sh
LAB_PYTHON="$(python3 -c 'import json; print(json.load(open(".local/config.json"))["python"])')"
./labctl doctor
"$LAB_PYTHON" scripts/build-type7a-runtime.py out/runs/NEW-TYPE7A-BUILD
"$LAB_PYTHON" scripts/check-type7a-runtime.py out/runs/NEW-BASELINE --baseline
"$LAB_PYTHON" scripts/with-type7a-runtime.py out/runs/NEW-TYPE7A-BUILD -- \
  scripts/check-type7a-runtime.py out/runs/NEW-NATIVE
"$LAB_PYTHON" -m unittest discover -s tests -v
./labctl test sine --replay
"$LAB_PYTHON" scripts/with-type7a-runtime.py out/runs/NEW-TYPE7A-BUILD -- \
  scripts/check-recorder-type7a-matrix.py out/runs/NEW-MATRIX-01
"$LAB_PYTHON" scripts/with-type7a-runtime.py out/runs/NEW-TYPE7A-BUILD -- \
  scripts/check-recorder-type7a-matrix.py out/runs/NEW-MATRIX-02
"$LAB_PYTHON" scripts/with-type7a-runtime.py out/runs/NEW-TYPE7A-BUILD -- \
  scripts/check-recorder-normal.py out/runs/NEW-NORMAL --prebuffer --queued-freeze
```

For the isolated complete SINE suite, create a fresh ignored run directory,
set `DT2_LAB_RUN_DIR` to its relative name under `out/runs`, then run the
explicit wrapper with `lab/worker.py test '{"machine":"sine"}'`. The retained
isolated SINE output is `sharc-type7a-isolated-sine-20261022-01/result.json`;
the normal labctl SINE manifest is `20261021T151234Z-test-19589495/manifest.json`.
Focused reports: `sharc-type7a-baseline-20261022-01/report.json` and
`sharc-type7a-native-20261022-04/report.json`. Upstream JUnit and its driver
are retained in the audit; logs are `out/sharc-type7a-*.log`.

The matrix driver's `runtime-selection.json` identifies the actual isolated
library/core and patch. The unchanged matrix's doctor provenance still lists
the original fixture library as an authenticated baseline input; it is not
the selected DSP engine. Source drift fails the driver and the matrix itself.

## Remaining boundary

The echo is a receipt, never permission to retire PCM or recycle identity.
Generation/snapshot storage stays pinned. The queued-trigger barrier, other
resource roots and composed carrier write ordering remain separate gates.
FREEZE is initiated by the existing test request serial and zero encoder turn;
native GUI polling queues its worker. This is not a long-press shortcut test.
The coupled playback machine is ONESHOT; no additional compatibility claim
for SLICE/GRID/WERP/REPITCH/STRETCH is made by this experiment.
Capture production, LP0 delivery/callback entry, CPU/DSP cadence and partial
startup remain modeled; the SEC error flags are retained. Native SAVE/readback,
real sequencer bar arming, full RTOS startup, physical DMA/cache/deadlines,
listening and device integration remain unverified. No hardware was flashed
or uploaded. No commit, push or publication occurred.
