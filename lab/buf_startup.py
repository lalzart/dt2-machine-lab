"""Opt-in pending BUF capture over stock recorder storage, OS1.16.

No PCM arena or loader bypass. Native batch boundaries gate later publication;
PHASE/OWN protect one take independently of the shared publication lease.
"""

from lab import buf_next_bar as b
from lab import recorder_freeze_code as n
from lab import recorder_freeze_worker_code as q
from lab import recorder_worker_code as w
from lab.emit import Code

BATCH_ACTIVE, BATCH_DONE, BATCH_SERIAL, BATCH_TASK, POISON = range(0x180, 0x194, 4)
PROJECT, ADMITTED_BATCH, CAPTURE_TASK, START_ALLOW = range(0x194, 0x1A4, 4)
SETUP_RETRY, SETUP_RETRY_TICK = 0x1A4, 0x1A8
SETUP_RETRY_FRAMES = 48000  # One second on the native sample clock, wrap-safe.
WAIT_LOAD = 6
# Reuse vacant space inside the existing disabled-diagnostic reservation.
# Its legacy disabled entry at +0x1000 remains intact; no DDR growth.
CODE = 0x10B00000
ARM_BODY = CODE + 0x1400
BATCH_ENTER, BATCH_LEAVE, POOL_GET = [CODE + x for x in (0x1C00, 0x1D00, 0x1E00)]
PREPARE, START_GATE, START_STOCK = [CODE + x for x in (0x2100, 0x2400, 0x2500)]
ARM_GATE, FREEZE_GATE, FREEZE_STOCK = [CODE + x for x in (0x2600, 0x2700, 0x3000)]
AUTO_GATE, AUTO_STOCK, ADMIT, PROJECT_GATE, PROJECT_STOCK = [
    CODE + x for x in (0x2800, 0x2C00, 0x2000, 0x3400, 0x3480)
]
INIT_GATE, INIT_STOCK = CODE + 0x3500, CODE + 0x3600
BATCH_SITE, BATCH_RETURN = 0x4004E97C, 0x4004EADA
BATCH_BYTES = bytes.fromhex("42af003842af003c")
RETURN_BYTES = bytes.fromhex("4cd77cfc4fef0058")
START_BYTES = bytes.fromhex("48780002206f0008")


def batch_enter(*, early_setup=None):
    c = Code()
    c.emit("4feffff0 48d70003")
    b.load(c, BATCH_ACTIVE)
    c.emit("4a80")
    c.branch(6, "poison")
    b.load(c, BATCH_SERIAL)
    c.imm("0c80", -1)
    c.branch(7, "poison")
    b.inc(c, BATCH_SERIAL)
    b.setv(c, SETUP_RETRY, 0)
    b.setv(c, BATCH_ACTIVE, 1)
    b.setv(c, BATCH_DONE, 0)
    c.imm("2039", q.CURRENT_TCB)
    b.store(c, BATCH_TASK)
    c.branch(0, "return")
    c.label("poison")
    b.setv(c, POISON, 1)  # Unknown nesting must never certify completion.
    c.label("return")
    if early_setup is not None:
        n.call(c, early_setup)
    c.emit("7000 2f400048 2f40004c 4cd70003 4fef0010")
    c.imm("4ef9", BATCH_SITE + 8)
    return c.finish(BATCH_ENTER)


def batch_leave():
    c = Code()
    c.emit("4feffff0 48d70003")
    b.load(c, BATCH_ACTIVE)
    c.imm("0c80", 1)
    c.branch(6, "return")
    c.imm("2039", q.CURRENT_TCB)
    b.load(c, BATCH_TASK, 1)
    c.emit("b081")
    c.branch(6, "return")  # The GUI also returns here after enqueueing.
    b.setv(c, BATCH_ACTIVE, 0)
    b.setv(c, BATCH_DONE, 1)
    c.label("return")
    c.emit("4cd70003 4fef0010")
    c.data.extend(RETURN_BYTES)
    c.imm("4ef9", BATCH_RETURN + 8)
    return c.finish(BATCH_LEAVE)


def pool_get():
    c = Code()
    n.call(c, 0x401988A2)
    c.emit("2f00")
    n.call(c, 0x40041D18, 4)
    c.emit("4a80")
    c.branch(7, "return")
    c.emit("2040 2250 22690028 2f08 4e91 588f 4a80")
    c.branch(7, "return")
    c.imm("0680", 0x1D2)
    c.label("return")
    c.emit("4e75")
    return c.finish(POOL_GET)


def admit():
    """Allow sample-operation overlap only within a witnessed startup batch."""
    c = Code()
    b.load(c, POISON)
    c.emit("4a80")
    c.branch(6, "bad")
    b.load(c, BATCH_SERIAL)
    c.emit("4a80")
    c.branch(7, "bad")
    b.load(c, BATCH_ACTIVE)
    c.imm("0c80", 1)
    c.branch(7, "good")
    b.load(c, BATCH_DONE)
    c.imm("0c80", 1)
    c.branch(6, "bad")
    for at in (q.STATE + 56, q.STOCK_BUSY):
        c.imm("2039", at)
        c.emit("4a80")
        c.branch(6, "bad")
    c.label("good")
    c.emit("7000 4e75")
    c.label("bad")
    c.emit("70ff 4e75")
    return c.finish(ADMIT)


def prepare():
    """0=retain/wait, 1=shared lease acquired, -1=setup/context failure."""
    c = Code()
    c.emit("4feffff0 48d70302")
    for field, value in ((POISON, 0), (BATCH_ACTIVE, 0), (BATCH_DONE, 1)):
        b.load(c, field)
        c.imm("0c80", value)
        c.branch(6, "wait")
    for at in (w.STATE + 12, n.STATE + 24, q.STATE + 56, q.STOCK_BUSY):
        c.imm("2039", at)
        c.emit("4a80")
        c.branch(6, "wait")
    n.call(c, INIT_STOCK)
    c.imm("2039", w.STATE + 64)
    c.imm("0c80", 1)
    c.branch(6, "bad")
    c.imm("2039", w.STATE + 68)
    b.load(c, b.POOL, 1)
    c.emit("b081")
    c.branch(6, "bad")
    n.call(c, b.CHECK)
    c.emit("4a80")
    c.branch(6, "bad")
    c.emit("7001")
    c.imm("23c0", w.STATE + 12)
    c.branch(0, "return")
    c.label("wait")
    c.emit("7000")
    c.branch(0, "return")
    c.label("bad")
    c.emit("70ff")
    c.label("return")
    c.emit("4cd70302 4fef0010 4e75")
    return c.finish(PREPARE)


def start_gate():
    c = Code()
    b.load(c, b.PHASE)
    c.emit("4a80")
    c.branch(7, "stock")
    b.load(c, START_ALLOW)
    c.imm("0c80", 1)
    c.branch(6, "busy")
    c.imm("2039", q.CURRENT_TCB)
    b.load(c, CAPTURE_TASK, 1)
    c.emit("b081")
    c.branch(6, "busy")
    c.emit("202f0004")
    b.load(c, b.CTRL, 1)
    c.emit("b081")
    c.branch(6, "busy")
    c.label("stock")
    c.imm("4ef9", START_STOCK)
    c.label("busy")
    c.emit("70ff 4e75")
    return c.finish(START_GATE)


def gate(address, fallback):
    c = Code()
    b.load(c, b.PHASE)
    c.emit("4a80")
    c.branch(7, "stock")
    c.emit("70f9 4e75")
    c.label("stock")
    c.imm("4ef9", fallback)
    return c.finish(address)


def arm_gate():
    c = Code()
    b.load(c, b.PHASE)
    c.emit("4a80")
    c.branch(7, "stock")
    c.imm("0c80", 1)
    c.branch(6, "busy")
    c.emit("2017")
    c.imm("0c80", b.ARM_CALLER)
    c.branch(6, "busy")
    c.imm("2039", w.DEST)
    c.emit("4a80")
    c.branch(7, "busy")
    c.label("stock")
    c.imm("4ef9", b.ARM)
    c.label("busy")
    c.emit("70f9 4e75")
    return c.finish(ARM_GATE)


def project_gate():
    c = Code()
    b.load(c, b.PHASE)
    c.emit("4a80")
    c.branch(7, "stock")
    b.setv(c, b.CANCEL, 1)
    c.label("stock")
    c.imm("4ef9", PROJECT_STOCK)
    return c.finish(PROJECT_GATE)


def init_gate():
    """Selector/poll setup must not reserve slots during a batch or capture."""
    c = Code()
    for field, value in ((b.PHASE, 0), (BATCH_ACTIVE, 0), (BATCH_DONE, 1), (POISON, 0)):
        b.load(c, field)
        c.imm("0c80", value)
        c.branch(6, "defer")
    c.imm("4ef9", INIT_STOCK)
    c.label("defer")
    c.emit("7000 4e75")
    return c.finish(INIT_GATE)


def payload():
    from lab import buf_auto_retirement as auto

    return {
        ARM_BODY: b.arm_only(
            diagnostics=True, performance_controls=True, startup_capture=True
        ),
        BATCH_ENTER: batch_enter(),
        BATCH_LEAVE: batch_leave(),
        POOL_GET: pool_get(),
        ADMIT: admit(),
        PREPARE: prepare(),
        START_GATE: start_gate(),
        START_STOCK: START_BYTES
        + bytes.fromhex("4ef9")
        + (b.START + 8).to_bytes(4, "big"),
        ARM_GATE: arm_gate(),
        FREEZE_GATE: gate(FREEZE_GATE, FREEZE_STOCK),
        AUTO_GATE: gate(AUTO_GATE, AUTO_STOCK),
        AUTO_STOCK: auto.step(),
        PROJECT_GATE: project_gate(),
        INIT_GATE: init_gate(),
        INIT_STOCK: b.initialize_buffers(setup_backoff=True),
    }
