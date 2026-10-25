# Isolated conditional MODIFY runtime

Approved 2026-10-22: implement conditional MODIFY in an isolated emulator
runtime, then rerun the existing replacement/FREEZE matrix. Continuation of
[the blocked running-path test](RECORDER-ACK-LOOP-RESULTS.md).

The artifact is a separately built native SHARC library, matching Python
semantics, instruction-check report and unchanged coupled recorder test.
Evidence is native instructions under modeled peripherals, not device timing.
This is emulator repair, with no new musical DSP algorithm or firmware edit.

## Semantics and scope

Normative source: Analog Devices, SHARC+ Core Programming Reference rev 1.5,
June 2023, sections 14-46 through 14-48 and 6-10:
[official manual](https://www.analog.com/media/en/dsp-documentation/processor-manuals/SC58x-2158x-prm.pdf#page=349).
In SISD, the predicate gates both MODIFY and parallel compute. Distinct source
I and M registers remain unchanged. Circular updates use B/L independently of
CBUFEN. Plain addressing is unscaled; SW scales by two, NW byte-space by four.
SIMD needs separate per-PE compute predicates and their OR for the shared DAG.

Selected boundary: add concrete SISD predicates to Type7a. Unknown predicates,
unknown mode and newly encountered SIMD conditional forms stop explicitly.
Use existing condition evaluation, scaling, wrap and compute helpers. Preserve
the old unconditional and NOT SV paths byte-for-byte in behavior; this is not
a general SIMD/ILAD/pipeline rewrite. Evaluate the predicate and snapshot
compute operands before writes. A false condition changes only instruction
progress, never data/compute flags. A true condition wraps the index, then
applies the compute result from old operands. Unsupported compute/length stops
before the index write. Existing arithmetic-width assumptions stay explicit.

## Isolation and ownership

Copy only pinned GPL-2.0 DigiKit tooling/native source into ignored output.
Apply one guarded lab-owned patch in that copy; retain upstream LICENSE and
hashes. Build offline with its existing locked Rust crates and Python tools.
Do not update pins, edit .deps, replace fixture libraries, install packages,
patch firmware opcodes or enable stale-library exceptions. An explicit runner
selects the matching copied Python tools and native library for one process;
all normal commands retain their baseline runtime.

No recorder or gesture changes. Existing frozen loop proposal/matrix remains
authoritative for BUF/FREEZE. Capture, cadence, partial startup and LP0 models
remain identified. Eight generations/snapshots stay pinned. No reuse, SAVE,
real bar arming, normal builder changes, hardware, commit or publication.

## Frozen experiment and acceptance

1. Preserve all current sources, tests, dependency trees and fixture hashes.
2. Falsifier: original stock opcode at SW 0x1cbc93 must still trap in the
   baseline runtime. The isolated runtime must execute its actual bytes with
   EQ true/false and correct NW-scaled I4, with no Python fallback.
3. Deterministic seed 0: compare Python/native state with independent expected
   results for EQ/NE and other SISD predicates, both DAG banks, source/dest
   aliases, signed modifiers, plain/SW/NW, forward/backward circular wrap,
   exact-length wrap, skipped invalid operands, parallel compute and flags.
   Unknown predicates/mode, unsupported SIMD, oversized circular modifiers
   and invalid compute must stop. Old 0x1f/0x17 cases retain baseline output.
4. Require strict whole-core generation, native/Python checks, existing
   relevant upstream tests, full lab unit suite, baseline SINE and isolated
   SINE exact output. Native instruction count is not hardware cycles.
5. Freeze sources; rerun scripts/check-recorder-ack-loop.py without editing
   its assertions or baseline expectations. Repeat the full timeline exactly.
   Require old-reader preservation, shared logical references, immutable frozen
   A, delay/drop/duplicate/stale/zero/recovery controls, original NORMAL return,
   native CPU source release and no host direct commit/receipt pump.
6. Retain fresh runs, exact inputs/captures, failed controls and source maps.
   Any further unsupported instruction is a new explicit blocker, never a NOP.

State equality: exact uregs, flags and progress for focused instruction cases;
exact all-32 voice work buffers/non-carrier replies and registered lifecycle
assertions for the coupled matrix. Initialization uses the existing prepared
fixture. Reset/panic/reconnect/rate change restart the isolated fixture; no
production implementation is claimed. Existing project persistence remains
guarded. Musical listening is N/A for the instruction repair; final DAC,
hardware timing/cache behavior and full RTOS startup remain unresolved.
