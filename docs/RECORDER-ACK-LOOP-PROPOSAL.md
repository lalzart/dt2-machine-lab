# Recorder acknowledgement control-path experiment

Approved increment, OS 1.16, 2026-10-21. The user authorized the next running
emulator test. Original transport glue; no musical algorithm, third-party DSP
port, normal builder change or device installation. Existing echo/observer
source and pinned GPL tooling remain unchanged.

Working artifact: `scripts/check-recorder-ack-loop.py` report. Evidence level:
target instructions under modeled peripherals and bounded event scheduling.

EVIDENCE: stock CPU frame ISR calls the real DSPI2 driver at `0x4002dd74`;
its return at `0x4002dd7a` pops four arguments then branches to `0x4002dd88`.
Install receipt matching at that return, preserving registers and the stack.
Do not call the diagnostic pump from Python. Successful BUF completion's
existing native FLUSH provides the request submission point; derive epoch,
identity and allocation extent from actual worker/stock allocator metadata.
This request is advisory only. A failed/missing receipt never frees anything.

EVIDENCE: the prepared DSP pack has MODE1/IMASK zero and lacks SEC reset
contents. Stock startup `0x1c0f24..0x1c0fa5` sets stacks, IVT location and
interrupt mode. Original call sites `0x1c8173..0x1c817a` and
`0x1c80a0..0x1c80a9` initialize SEC and SPI2. The pinned descriptor DMA model
raises sources 69/70. With architectural stack/bank models enabled, original
IVT/SEC/SSL dispatch reaches `0x1c77b4` without explicit callback entry;
both sources return to zero and IMASKP clears. Startup also leaves modeled
SEC error flags; retain and report them, never mask them as clean boot proof.

SELECTED: an opt-in CPU overlay composing with the native queued BUF/FREEZE
experiment, plus paired stock/echo DSP engines. Run the original task's block
call site `0x1c7756..0x1c775d` after each SPI event. Host schedules cadence;
native interrupt logic selects, acknowledges, dispatches and ends completion.
LP0 delivery/callback entry remains the established explicit model. Stop at
safe call boundaries; this is not full DSP RTOS startup or real-time coupling.
No new DSP kernel or echo protocol change is planned.

## Frozen experiment and controls

Deterministic seed zero, stereo arithmetic PCM A then B. Timeline: warm up
NORMAL, select BUF 1 using C, record/USE A, select shared T5, queue FREEZE A,
select snapshot on T6, play, re-record B, trigger shared tracks and frozen A.
Exercise native-produced echo carrier delay, drop, duplicate, stale replay,
zero replies and recovery with a newer request. Fault injection changes only
the carrier; it never writes receipt state. Test completion absence by masking
SEC in an isolated negative fixture. Reject unknown firmware/patch sites.

Acceptance: original CPU ISR/worker/queue runs without host direct commands;
all 32 voice buffers and non-carrier replies match the paired stock engine
exactly. Source PCM is retired by the existing worker, generation and snapshot
allocations stay pinned, stable slots survive replacement, frozen A remains
unchanged, no stale or missing reply reports receipt. Negative controls must
fail closed. Preserve all inherited sources and expected baselines.

## State/control and failure contract

No gesture changes. NORMAL retains its stock path. BUF USE submits one
diagnostic request only after native publication; FREEZE retains its existing
queue and immutable root. Receipt state remains NONE/PENDING/CONFIRMED_RECEIPT/
TIMED_OUT, with the unchanged 48-fragment/192-poll protocol. Repeated recording
increments sequence. Faults retain allocations. Project persistence remains
guarded. Reset/reconnect/panic/rate changes are not production implementations;
restart the isolated fixture, keep reuse disabled. Eight issued generations
and eight snapshots remain the finite admission bounds. No SAVE/readback.

Retain fresh ignored runs, source maps, exact repeat, native instruction
observations, fault traces and failures. Run focused native units, complete
unit suite, SINE replay, atomic-publication regression and original echo test.
Do not change the prior modules, dependencies, Flex, Plaits, Capicola or normal
firmware builders. No hardware, commit, push or publication.

UNRESOLVED: physical DMA/cache/interrupt timing, full RTOS startup, composed
carrier ownership/write ordering, queued-trigger retirement barrier, identity
recycling, continuous capture producer, native readback/SAVE and real bar clock.
These remain separate even if this experiment passes.
