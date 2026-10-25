"""Opt-in OS 1.16 FREEZE job on the original background service.

All pointers below are emulator-owned scratch except authenticated stock sites.
No DSP allocation or identity is retired here.
"""

import struct

from lab import recorder_freeze_code as n
from lab import recorder_worker_code as w
from lab.emit import Code

BASE, END = 0x10700000, 0x10704000
STATE = BASE
POLL, SUBMIT, MANAGER = BASE + 0x1000, BASE + 0x1200, BASE + 0x1500
WORKER, DONE, GATE = BASE + 0x1600, BASE + 0x1800, BASE + 0x1900
ENTER, LEAVE = BASE + 0x1C00, BASE + 0x1D00
BODY, TRAMP, GUARDS = BASE + 0x2000, BASE + 0x3000, BASE + 0x3100
LABEL = BASE + 0x300
GUI = 0x40033D00
GUI_BYTES = bytes.fromhex("487940966f3c")
CURRENT_TCB = 0x47DB3F64  # Authenticated scheduler at 0x40000418.
STOCK_BUSY = 0x405B1360
# Opt-in diagnostic metadata only; no lease, count or recorder state lives here.
(
    OP_SITE,
    OP_CALLER,
    OP_ARG1,
    OP_ARG2,
    OP_TASK,
    OP_TICK,
    OP_SP,
    OP_RETURNED,
    OP_ENTERS,
    OP_EXITS,
    OP_SERIAL,
) = range(0x80, 0xAC, 4)
OP_FIELDS = tuple(range(0x80, 0xAC, 4))
# request serial, handled serial, phase, result, destination, epoch, kit,
# owner TCB, completion count, queued count, fault seam, refusal count, lease.


def poll():
    c = Code()
    c.emit("4feffff0 48d70303")  # Preserve D0/D1/A0/A1 at the stock boundary.
    c.imm("2039", STATE)
    c.imm("2239", STATE + 4)
    c.emit("b081")
    c.branch(7, "done")
    c.imm("23c0", STATE + 4)
    n.call(c, SUBMIT)
    c.label("done")
    c.emit("4cd70303 4fef0010")
    c.imm("4ef9", TRAMP)
    return c.finish(POLL)


def submit(*, address=SUBMIT, admission=None, queue_failure=None):
    c = Code()
    c.emit("4fefffb0 48d70c0c")  # D2/D3/A2/A3 and two local std::functions.
    if admission is not None:
        # Explicit BUF entry: admission(buf) atomically validates and claims
        # the existing mutation lease, then supplies the same queue context.
        c.emit("2f2f0054")
        n.call(c, admission, 4)
        c.emit("4a80")
        c.branch(6, "reject")
        c.branch(0, "queue")
    for at in (w.STATE + 12, n.STATE + 24, STOCK_BUSY, STATE + 56):
        c.imm("2039", at)
        c.emit("4a80")
        c.branch(6, "busy")
    c.imm("2039", w.DEST)
    c.imm("0c80", 1)
    c.branch(5, "bad")
    c.imm("0c80", 4)
    c.branch(2, "bad")
    c.imm("23c0", STATE + 16)
    c.imm("2039", n.STATE)
    c.imm("23c0", STATE + 20)
    c.imm("2039", 0x80004704)
    c.imm("23c0", STATE + 24)
    c.emit("7002")
    c.imm("23c0", w.STATE + 12)
    c.emit("7001")
    c.imm("23c0", STATE + 8)
    c.emit("7000")
    for at in (STATE + 28, STATE + 48):
        c.imm("23c0", at)
    c.label("queue")
    c.imm("45f9", STATE)
    c.imm("203c", MANAGER)
    c.imm("223c", WORKER)
    c.emit("7400 2f4a0010 2f420014 2f400018 2f41001c")
    c.imm("223c", DONE)
    c.emit("2f4a0020 2f420024 2f400028 2f41002c")
    n.call(c, 0x40198A16)  # Existing worker service singleton.
    c.emit("2600 47ef0020 45ef0010 2f0b 2f0a")
    c.imm("4879", LABEL)
    c.emit("2f03")
    n.call(c, 0x400F0AB8, 16)
    c.emit("4a80")
    c.branch(7, "queue_fail")
    c.imm("2039", STATE + 36)
    c.emit("5280")
    c.imm("23c0", STATE + 36)
    c.emit("7000")
    c.branch(0, "return")
    c.label("queue_fail")
    c.emit("7000")
    c.imm("23c0", w.STATE + 12)
    if queue_failure is not None:
        n.call(c, queue_failure)
    c.emit("70fa")
    c.branch(0, "reject")
    c.label("bad")
    c.emit("70ff")
    c.branch(0, "reject")
    c.label("busy")
    c.emit("70f9")
    c.label("reject")
    # A refused second request must not clobber the first request's result,
    # latched context or pending ownership.
    c.imm("2239", STATE + 44)
    c.imm("0681", 1)
    c.imm("23c1", STATE + 44)
    c.label("return")
    c.imm("23c0", STATE + 52)
    c.emit("4cd70c0c 4fef0050 4e75")
    return c.finish(address)


def manager():
    """Stock std::function manager ABI; immutable state pointer, no allocation."""
    c = Code()
    c.emit("202f000c")
    c.imm("0c80", 2)
    c.branch(6, "done")
    c.emit("206f0004 226f0008 20d9 20d9")
    c.label("done")
    c.emit("7000 4e75")
    return c.finish(MANAGER)


def gate():
    c = Code()
    for at, value in ((w.STATE + 12, 2), (STATE + 8, 2), (STATE + 48, 1)):
        c.imm("2039", at)
        c.imm("0c80", value)
        c.branch(6, "deny")
    c.imm("2039", STATE + 28)
    c.imm("2239", CURRENT_TCB)
    c.emit("b081")
    c.branch(6, "deny")
    c.emit("4a80")
    c.branch(7, "deny")
    for actual, latched in ((n.STATE, STATE + 20), (0x80004704, STATE + 24)):
        c.imm("2039", actual)
        c.imm("2239", latched)
        c.emit("b081")
        c.branch(6, "deny")
    c.emit("7000 4e75")
    c.label("deny")
    c.emit("70ff 4e75")
    return c.finish(GATE)


def worker():
    c = Code()
    c.emit("4feffff4 48d70c04")
    c.imm("45f9", STATE)
    c.imm("2039", w.STATE + 12)
    c.imm("0c80", 2)
    c.branch(6, "bad")
    c.emit("202a0008")
    c.imm("0c80", 1)
    c.branch(6, "bad")
    for at in (STOCK_BUSY, STATE + 56):
        c.imm("2039", at)
        c.emit("4a80")
        c.branch(6, "bad")
    c.imm("2039", CURRENT_TCB)
    c.emit("2540001c 7002 25400008 7001 25400030")
    c.emit("202a0014 222a0018 242a0028")
    c.imm("0c82", 3)  # Native stale-context fault seams, not a host commit.
    c.branch(6, "kit_fault")
    c.imm("0680", 1)
    c.label("kit_fault")
    c.imm("0c82", 4)
    c.branch(6, "arguments")
    c.imm("0681", 1)
    c.label("arguments")
    c.emit("2f01 2f00 2f2a0010")
    n.call(c, BODY, 12)
    c.emit("7200 25410030")
    c.branch(0, "return")
    c.label("bad")
    c.emit("70ff")
    c.label("return")
    c.emit("4cd70c04 4fef000c 4e75")
    return c.finish(WORKER)


def done():
    c = Code()
    c.emit("202f0008")  # Stock completion passes the worker's integer result.
    c.imm("23c0", STATE + 12)
    c.imm("2039", STATE + 32)
    c.emit("5280")
    c.imm("23c0", STATE + 32)
    c.emit("7003")
    c.imm("23c0", STATE + 8)
    c.emit("7000")
    c.imm("23c0", w.STATE + 12)
    c.imm("23c0", STATE + 48)
    c.emit("4e75")
    return c.finish(DONE)


def operation_count(address, delta, *, diagnostics=False):
    """Atomic count update; only this short register-only sequence masks IRQs."""
    c = Code()
    c.emit("2f02 40c2 2002")
    c.imm("0080", 0x700)
    c.emit("46c0")
    c.imm("2039", STATE + 56)
    if diagnostics:
        if delta == 1:
            c.emit("4a80")
            c.branch(6, "trace_done")
            for instruction, field in (
                ("202f0004", OP_SITE),  # Return to guarded wrapper.
                ("202f0018", OP_CALLER),  # Wrapper's original caller.
                ("202f001c", OP_ARG1),
                ("202f0020", OP_ARG2),
            ):
                c.emit(instruction)
                c.imm("23c0", STATE + field)
            for source, field in ((CURRENT_TCB, OP_TASK), (0x40966500, OP_TICK)):
                c.imm("2039", source)
                c.imm("23c0", STATE + field)
            c.emit("200f")
            c.imm("0680", 4)  # ENTER frame before the saved D2.
            c.imm("23c0", STATE + OP_SP)
            c.emit("7000")
            c.imm("23c0", STATE + OP_RETURNED)
            c.imm("2039", STATE + OP_ENTERS)
            c.emit("5280")
            c.imm("23c0", STATE + OP_SERIAL)
        else:
            c.emit("200f")
            c.imm("0680", 4)
            # CMP absolute memory,D0 would extend the audited ISA subset.
            # Compare using saved D2 after saving the interrupt mask on stack.
            c.emit("2f02")
            c.imm("2439", STATE + OP_SP)
            c.emit("b082 4cd70004 4fef0004")  # Restore D2 without changing CCR.
            c.branch(6, "trace_done")
            c.emit("7001")
            c.imm("23c0", STATE + OP_RETURNED)
        c.label("trace_done")
        field = OP_ENTERS if delta == 1 else OP_EXITS
        c.imm("2039", STATE + field)
        c.emit("5280")
        c.imm("23c0", STATE + field)
        c.imm("2039", STATE + 56)
    c.imm("0680", delta)
    c.imm("23c0", STATE + 56)
    c.emit("46c2 241f 4e75")
    return c.finish(address)


def slot_guard(address, fallback, *, load):
    c = Code()
    c.emit("4feffff0 48d70c0c")
    n.call(c, ENTER)
    c.imm("2039", w.STATE + 12)
    c.imm("0c80", 2)
    c.branch(6, "stock")
    n.call(c, GATE)
    c.emit("4a80")
    c.branch(6, "deny")
    c.label("stock")
    c.emit("242f0014")
    if load:
        c.emit("262f0018 2f03")
    c.emit("2f02")
    n.call(c, fallback, 8 if load else 4)
    c.emit("2400")
    c.branch(0, "return")
    c.label("deny")
    c.emit("74ff" if load else "7400")
    c.label("return")
    n.call(c, LEAVE)
    c.emit("2002 4cd70c0c 4fef0010 4e75")
    return c.finish(address)


def payload(*, operation_diagnostics=False):
    parts = {
        POLL: poll(),
        SUBMIT: submit(),
        MANAGER: manager(),
        WORKER: worker(),
        DONE: done(),
        GATE: gate(),
        ENTER: operation_count(ENTER, 1, diagnostics=operation_diagnostics),
        LEAVE: operation_count(LEAVE, -1, diagnostics=operation_diagnostics),
        BODY: n.freeze(address=BODY, worker_gate=GATE),
        TRAMP: GUI_BYTES + b"\x4e\xf9" + struct.pack(">I", GUI + len(GUI_BYTES)),
    }
    for i in range(3):
        at = GUARDS + i * 0x100
        parts[at] = slot_guard(at, w.SLOT_GUARDS + i * 256, load=i == 0)
    ordered = sorted(parts.items())
    for (a, b), (next_a, _) in zip(ordered, ordered[1:], strict=False):
        if a + len(b) > next_a:
            raise ValueError(f"FREEZE worker overlap {a:#x}")
    return parts
