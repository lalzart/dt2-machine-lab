"""Native BUF publication; recorder DEST is independent of track selection."""

import struct

from lab import arp_firmware as bridge
from lab import buf_auto_retirement as auto
from lab import buf_performance as perf
from lab import recorder_freeze_code as n
from lab import recorder_freeze_worker_code as q
from lab import recorder_worker_code as w
from lab.emit import Code
from lab.project import ROOT, read_json, require, sha256

BASE, END = 0x11000000, 0x11008000
STATE = BASE
PHASE, RESULT, ARMS, STARTS, STOPS, USES, CANCELS = range(0, 28, 4)
DEST, TRACK, KIT, EPOCH, CTRL, POOL, CLOCK_EPOCH, AFTER = range(28, 60, 4)
START_BAR, START_EDGE, START_TICK, STOP_EDGE, STOP_TICK = range(60, 80, 4)
JOB_RESULT, CANCEL, OWN = 80, 84, 88
PUBLISH_TICK, QUEUE_TICK = 92, 96
NORMAL_DEST = 100  # Recorder UI setting; independent of the admitted target.
DURATION_BARS, LAST_BAR = 104, 108  # Latched duration and serviced bar receipt.
PUBLISHES = USES  # Retain the existing trace ABI; publication never assigns.
SERIAL, CEPOCH, LAST_STEP, LIVE, PATTERN, ENABLED = range(0x100, 0x118, 4)
PRIMED, EDGE_TICK, DISCONTINUITIES, VALID = range(0x118, 0x128, 4)
WRAPPED = 0x128
ARM_DIAG, ARM_DIAG_VALUE = 0x12C, 0x130  # Opt-in, outside admitted transaction state.
OP_SNAPSHOT = BASE + 0x5E00
OP_CONTEXT = 0x140  # Latched under the same mask as the observed sample count.
CLOCK_DIAG, CLOCK_DIAG_VALUE, CLOCK_HITS = 0x134, 0x138, 0x13C
CLOCK_DIAGNOSTICS = (
    "NOIRQ",
    "STOP",
    "PATTERN",
    "LEN",
    "PATMODE",
    "SCALE",
    "STEP",
    "SERIAL",
)
SETTINGS, LABEL = BASE + 0x200, BASE + 0x300
ARM, IRQ, POLL, STEP, CHECK, QUEUE = [
    BASE + x for x in (0x1000, 0x1800, 0x2400, 0x2500, 0x3000, 0x3800)
]
WORKER, DONE, CANCEL_FN, ARM_STOCK, INPUT = [
    BASE + x for x in (0x3E00, 0x4000, 0x4800, 0x5000, 0x5200)
]
INIT = BASE + 0x5400
INIT_BODY, ARM_ONLY = BASE + 0x5600, BASE + 0x5800
USE_GATE, USE_STOCK = BASE + 0x5C00, BASE + 0x5D00
ARM_BUSY, ARM_REFUSED, ARM_LENGTH = -7, -1, -6
# First failing check, observed value, and unchanged admission result ABI.
ARM_DIAGNOSTICS = (
    ("REQUEST", ARM_BUSY),
    ("BUF", ARM_REFUSED),
    ("WORKER", ARM_BUSY),
    ("FREEZE", ARM_BUSY),
    ("LOCK", ARM_BUSY),
    ("LOADER", ARM_BUSY),
    ("PLAY", ARM_REFUSED),
    ("CTRL", ARM_REFUSED),
    ("RECORDER", ARM_BUSY),
    ("LENGTH", ARM_LENGTH),
    ("CLOCK", ARM_REFUSED),
    ("MODE", ARM_REFUSED),
    ("SETUP", ARM_REFUSED),
    ("POOL", ARM_REFUSED),
    ("KIT", ARM_REFUSED),
)
CAPACITY_RESULT = -8
MAX_CAPTURE_FRAMES = 480000  # Existing ten-second BUF take limit, not Flex's limit.
RLEN_GET = 0x4004CC42
RLEN = 4  # Default 16 steps; OS 1.16 uses 1 << raw, and raw 8 is MAX.
RLEN_BARS = {4: 1, 5: 2, 6: 4}
CAPTURE_SETTINGS = (0, 4, 12, 16, 20)  # Source, threshold, R.LEN, channel, start.
ARM_SITE, ARM_CALLER, CLOCK_SITE = 0x40015F9C, 0x40016BAE, 0x400D8C6E
ARM_BYTES = bytes.fromhex("48780001206f0008")
CLOCK_BYTES = bytes.fromhex("4cd77fff4fef0094")
START, STOP, DISCARD, READY = 0x40015FDA, 0x400162C0, 0x40015FF8, 0x40016020
COUNT, CHANNEL, CLOCK_MODE, TICK = 0x40015F7C, 0x4004CCA2, 0x40138C88, 0x40966500
CLOCK_VALUE = 0  # Measured native selector getter, raw word 0x402b62c0 == 1.
LATENCY = 8192
MASTER = bytes.fromhex("001000010800020000ff0000")


def contract():
    c = read_json(ROOT / "machines/buf-next-bar/contract.json")
    require(c["status"] == "ready", "Next-bar contract not ready")
    require(sha256(ROOT / c["proposal"]) == c["proposal_sha256"], "Next-bar plan drift")
    require(
        c["dependencies"] == read_json(ROOT / "deps.lock.json"), "Next-bar pins drift"
    )
    for field in (
        "approval",
        "working_artifact",
        "controls",
        "state_matrix",
        "source_equivalence",
        "experiment",
        "validation",
        "results",
        "gaps",
        "decisions",
    ):
        require(bool(c[field]), "Incomplete next-bar contract: " + field)
    require(
        c["constants"]
        == dict(
            BASE=BASE,
            END=END,
            CLOCK_SITE=CLOCK_SITE,
            ARM_SITE=ARM_SITE,
            ARM_CALLER=ARM_CALLER,
            LATENCY=LATENCY,
            BARS=1,
            RLEN=RLEN,
            SUPPORTED_RLEN=list(RLEN_BARS),
            MAX_CAPTURE_FRAMES=MAX_CAPTURE_FRAMES,
        ),
        "Next-bar constants drift",
    )
    return c


def load(c, off, reg=0):
    c.imm(f"{0x2039 | (reg << 9):04x}", STATE + off)


def store(c, off, reg=0):
    c.imm(f"{0x23C0 | reg:04x}", STATE + off)


def setv(c, off, value):
    c.imm("203c", value)
    store(c, off)


def inc(c, off):
    load(c, off)
    c.emit("5280")
    store(c, off)


def controller(c, function):
    load(c, CTRL)
    c.emit("2f00")
    n.call(c, function, 4)


def selected(c):
    n.call(c, 0x401988A2)
    c.emit("2f00")
    n.call(c, 0x40041D18, 4)
    c.emit("2f00")
    n.call(c, 0x4004ABE8, 4)


def initialize():
    """Reserve/name empty logical slots on the GUI thread, without PCM commit."""
    c = Code()
    c.imm("2039", w.DEST)
    c.emit("4a80")
    c.branch(7, "return")
    c.imm("4ef9", INIT_BODY)
    c.label("return")
    c.emit("4e75")
    return c.finish(INIT)


def initialize_buffers():
    """Shared empty-BUF setup, including an explicit request at DEST=NORMAL."""
    c = Code()
    c.emit("4feffff0 48d70303")
    c.imm("2039", w.STATE + 64)
    c.emit("4a80")
    c.branch(6, "return")
    for at in (w.STATE + 12, n.STATE + 24, q.STOCK_BUSY, q.STATE + 56):
        c.imm("2039", at)
        c.emit("4a80")
        c.branch(6, "return")
    c.emit("7001")
    c.imm("23c0", w.STATE + 12)
    n.call(c, w.SETUP)
    c.emit("4a80")
    c.branch(6, "release")
    c.imm("41f9", w.STATE + 96)
    c.imm("43f9", n.STATE + 32)
    for _ in range(4):
        c.emit("22d8")
    c.label("release")
    c.emit("7000")
    c.imm("23c0", w.STATE + 12)
    c.label("return")
    c.emit("4cd70303 4fef0010 4e75")
    return c.finish(INIT_BODY)


def master(c, bad, *, semantic=False, diagnostics=False):
    def failure(name):
        return "clock_" + name if diagnostics else bad

    c.imm("2079", 0x4316501C)
    c.emit("2008 4a80")
    c.branch(7, failure("PATTERN"))
    c.imm("d1fc", 0x1DB74)
    if semantic:
        # OS1.16 source44/start consume length(+0), mode(+5), scale(+6).
        # Other bytes in MASTER belong to the fixture, not this clock contract.
        for instruction, value, name in (
            ("3010", 16, "LEN"),
            ("10280005", 0, "PATMODE"),
            ("10280006", 2, "SCALE"),
        ):
            c.emit("7000 " + instruction)
            c.imm("0c80", value)
            c.branch(6, failure(name))
        return
    for i in range(3):
        c.emit("2018")
        c.imm("0c80", int.from_bytes(MASTER[i * 4 : i * 4 + 4], "big"))
        c.branch(6, bad)


def irq(*, clock_fix=False):
    c = Code()
    c.emit("4feffff0 48d70303")
    load(c, ENABLED)
    c.emit("4a80")
    c.branch(7, "return")
    if clock_fix:
        inc(c, CLOCK_HITS)
        # Pure three-instruction stock getter; same predicate as ARM/CHECK.
        n.call(c, perf.PLAY_GET)
        c.imm("0c80", 1)
        c.branch(6, "clock_STOP")
    else:
        for at in (0x43164F94, 0x43165010):
            c.imm("2039", at)
            c.imm("0c80", 1)
            c.branch(6, "invalid")
    master(c, "invalid", semantic=clock_fix, diagnostics=clock_fix)
    c.imm("2039", 0x4316501C)
    load(c, PATTERN, 1)
    c.emit("b081")
    c.branch(6, "prime")
    load(c, VALID)
    c.emit("4a80")
    c.branch(7, "prime")
    c.emit("7000")
    c.imm("3039", 0x43164F98)
    load(c, LAST_STEP, 1)
    c.emit("b081")
    c.branch(7, "return")
    c.imm("0681", 1)
    c.imm("0281", 15)
    c.emit("b081")
    c.branch(6, "prime")
    store(c, LAST_STEP)
    c.emit("4a80")
    c.branch(7, "wrapped")
    c.imm("0c80", 1)
    c.branch(6, "return")
    load(c, WRAPPED)
    c.imm("0c80", 1)
    c.branch(6, "return")
    setv(c, WRAPPED, 0)
    load(c, SERIAL)
    c.imm("0c80", -1)
    c.branch(7, "clock_SERIAL" if clock_fix else "invalid")
    c.imm("2039", TICK)
    store(c, EDGE_TICK)
    inc(c, SERIAL)  # Publish the receipt last, after its timestamp.
    c.branch(0, "return")
    c.label("wrapped")
    setv(c, WRAPPED, 1)
    c.branch(0, "return")
    c.label("prime")
    inc(c, CEPOCH)
    inc(c, DISCONTINUITIES)
    c.imm("2039", 0x4316501C)
    store(c, PATTERN)
    c.emit("7000")
    c.imm("3039", 0x43164F98)
    c.imm("0c80", 15)
    c.branch(2, "clock_STEP" if clock_fix else "invalid")
    store(c, LAST_STEP)
    setv(c, VALID, 1)
    setv(c, PRIMED, 1)
    setv(c, WRAPPED, 0)
    c.branch(0, "return")
    if clock_fix:
        for reason, name in enumerate(CLOCK_DIAGNOSTICS[1:], 1):
            c.label("clock_" + name)
            store(c, CLOCK_DIAG_VALUE)
            setv(c, CLOCK_DIAG, reason)
            c.branch(0, "invalid")
    c.label("invalid")
    load(c, VALID)
    c.emit("4a80")
    c.branch(7, "return")
    inc(c, CEPOCH)
    setv(c, VALID, 0)
    c.label("return")
    c.emit("4cd70303 4fef0010")
    c.data.extend(CLOCK_BYTES)
    c.imm("4ef9", CLOCK_SITE + 8)
    return c.finish(IRQ)


def arm():
    """Keep the stock caller guard and legacy second-chord cancellation."""
    c = Code()
    c.emit("2017")
    c.imm("0c80", ARM_CALLER)
    c.branch(6, "stock")
    c.imm("2039", w.DEST)
    c.emit("4a80")
    c.branch(7, "stock")
    load(c, PHASE)
    c.imm("0c80", 1)
    c.branch(7, "cancel")
    c.imm("2f39", w.DEST)
    c.emit("2f2f0008")  # Original controller argument, after the BUF push.
    n.call(c, ARM_ONLY, 8)
    c.emit("4a80")
    c.branch(7, "return")
    store(c, RESULT)
    c.emit("70ff")  # Preserve the stock wrapper's boolean failure ABI.
    c.label("return")
    c.emit("4e75")
    c.label("cancel")
    n.call(c, CANCEL_FN)
    c.emit("7000 4e75")
    c.label("stock")
    c.imm("4ef9", ARM_STOCK)
    return c.finish(ARM)


def arm_only(*, diagnostics=False, operation_diagnostics=False):
    """GUI-thread ABI (controller*, BUF 1..4); never toggle or change UI DEST.

    Refusals return in D0 without modifying an admitted transaction. Only the
    guarded legacy wrapper retains its second-chord cancellation semantics.
    """
    c = Code()
    failures = {}

    def fail(condition, target, reason, reg=0):
        if diagnostics:
            index = next(
                i for i, item in enumerate(ARM_DIAGNOSTICS, 1) if item[0] == reason
            )
            label = f"diagnostic_{index}"
            failures[label] = (index, reg, ARM_DIAGNOSTICS[index - 1][1])
            c.branch(condition, label)
        else:
            c.branch(condition, target)

    c.emit("4fefffd0 48d77cfc 242f0034 262f0038")
    load(c, PHASE)
    c.emit("4a80")
    fail(6, "busy", "REQUEST")
    c.imm("0c83", 1)
    fail(5, "refuse", "BUF", 3)
    c.imm("0c83", 4)
    fail(2, "refuse", "BUF", 3)
    for at, reason in (
        (w.STATE + 12, "WORKER"),
        (q.STATE + 56, "FREEZE"),
        (n.STATE + 24, "LOCK"),
        (q.STOCK_BUSY, "LOADER"),
    ):
        if operation_diagnostics and reason == "FREEZE":
            n.call(c, OP_SNAPSHOT)
        else:
            c.imm("2039", at)
        c.emit("4a80")
        fail(6, "busy", reason)
    n.call(c, perf.PLAY_GET)
    c.imm("0c80", 1)
    fail(6, "refuse", "PLAY")
    c.emit("4a82")
    fail(7, "refuse", "CTRL", 2)
    c.emit("2f02")
    n.call(c, auto.RECORDER_STATE, 4)
    c.emit("4a80")
    fail(6, "busy", "RECORDER")
    n.call(c, 0x401988A2)
    c.emit("2f00")
    n.call(c, 0x40041D18, 4)
    c.emit("2f00")
    n.call(c, RLEN_GET, 4)
    for raw, bars in RLEN_BARS.items():
        c.imm("0c80", raw)
        c.branch(7, f"bars{bars}")
    fail(0, "length", "LENGTH")
    for bars in RLEN_BARS.values():
        c.label(f"bars{bars}")
        c.imm("283c", bars)  # D4 survives the original native service calls.
        c.branch(0, "supported_length")
    c.label("supported_length")
    load(c, VALID)
    c.imm("0c80", 1)
    fail(6, "refuse", "CLOCK")
    n.call(c, CLOCK_MODE)
    c.imm("0c80", CLOCK_VALUE)
    fail(6, "refuse", "MODE")
    # Setup uses stock project/slot helpers and never writes recorder DEST.
    n.call(c, INIT_BODY)
    for at, reason in (
        (w.STATE + 64, "SETUP"),
        (w.STATE + 68, "POOL"),
        (0x80004704, "KIT"),
    ):
        c.imm("2039", at)
        c.emit("4a80")
        fail(7, "refuse", reason)
    store(c, DURATION_BARS, 4)
    store(c, DEST, 3)
    store(c, CTRL, 2)
    selected(c)
    store(c, TRACK)
    for actual, field in (
        (0x80004704, KIT),
        (n.STATE, EPOCH),
        (w.STATE + 68, POOL),
        (STATE + CEPOCH, CLOCK_EPOCH),
        (STATE + SERIAL, AFTER),
        (w.DEST, NORMAL_DEST),
    ):
        c.imm("2039", actual)
        store(c, field)
    load(c, POOL)
    c.emit("2040")
    c.imm("d1fc", -36)
    c.imm("43f9", SETTINGS)
    for _ in range(9):
        c.emit("22d8")
    setv(c, CANCEL, 0)
    setv(c, OWN, 1)
    c.emit("7001")
    c.imm("23c0", w.STATE + 12)
    setv(c, PHASE, 1)
    setv(c, RESULT, 0)
    if diagnostics:
        store(c, ARM_DIAG)
        store(c, ARM_DIAG_VALUE)
    inc(c, ARMS)
    c.emit("7000")
    c.branch(0, "return")
    c.label("refuse")
    c.imm("203c", ARM_REFUSED)
    c.branch(0, "return")
    c.label("length")
    c.imm("203c", ARM_LENGTH)
    c.branch(0, "return")
    c.label("busy")
    c.imm("203c", ARM_BUSY)
    if diagnostics:
        c.branch(0, "return")
        for label, (index, reg, result) in failures.items():
            c.label(label)
            store(c, ARM_DIAG_VALUE, reg)  # Capture the value used by this branch.
            setv(c, ARM_DIAG, index)
            c.imm("203c", result)
            c.branch(0, "return")
    c.label("return")
    c.emit("4cd77cfc 4fef0030 4e75")
    return c.finish(ARM_ONLY)


def operation_snapshot():
    """Read count and diagnostic context together; never clear or claim a guard."""
    c = Code()
    c.emit("4feffff0 48d70004 40c2 2002")
    c.imm("0080", 0x700)
    c.emit("46c0")
    for index, field in enumerate(q.OP_FIELDS):
        c.imm("2039", q.STATE + field)
        store(c, OP_CONTEXT + index * 4)
    c.imm("2039", q.STATE + 56)
    c.emit("46c2 4cd70004 4fef0010 4e75")
    return c.finish(OP_SNAPSHOT)


def check(*, clock_fix=False):
    c = Code()
    c.emit("4feffff0 48d70302")  # D1/A0/A1; return in D0.
    for actual, field in (
        (n.STATE, EPOCH),
        (0x80004704, KIT),
        (w.STATE + 68, POOL),
        (STATE + CEPOCH, CLOCK_EPOCH),
        (w.DEST, NORMAL_DEST),
    ):
        c.imm("2039", actual)
        load(c, field, 1)
        c.emit("b081")
        c.branch(6, "bad")
    for off, value in ((OWN, 1), (VALID, 1), (CANCEL, 0)):
        load(c, off)
        c.imm("0c80", value)
        c.branch(6, "bad")
    c.imm("2039", w.STATE + 12)
    c.imm("0c80", 1)
    c.branch(6, "bad")
    n.call(c, perf.PLAY_GET)
    c.imm("0c80", 1)
    c.branch(6, "bad")
    n.call(c, CLOCK_MODE)
    c.imm("0c80", CLOCK_VALUE)
    c.branch(6, "bad")
    load(c, POOL)
    c.emit("2040")
    c.imm("d1fc", -36)
    c.imm("43f9", SETTINGS)
    for off in CAPTURE_SETTINGS:
        c.emit(f"2028{off:04x} 2229{off:04x} b081")
        c.branch(6, "bad")
    master(c, "bad", semantic=clock_fix)
    c.emit("7000")
    c.branch(0, "return")
    c.label("bad")
    c.emit("70ff")
    c.label("return")
    c.emit("4cd70302 4fef0010 4e75")
    return c.finish(CHECK)


def poll():
    c = Code()
    c.emit("4feffff0 48d70303")
    n.call(c, INIT)
    n.call(c, STEP)
    c.emit("4cd70303 4fef0010")
    c.imm("4ef9", auto.POLL)
    return c.finish(POLL)


def step():
    c = Code()
    c.emit("4fefffd0 48d77cfc")
    load(c, PHASE)
    c.emit("4a80")
    c.branch(7, "return")
    c.imm("0c80", 5)
    c.branch(7, "cancel")
    n.call(c, CHECK)
    c.emit("4a80")
    c.branch(6, "cancel")
    load(c, PHASE)
    c.imm("0c80", 4)
    c.branch(7, "return")
    c.imm("0c80", 3)
    c.branch(7, "normalizing")
    controller(c, auto.RECORDER_STATE)
    load(c, PHASE, 1)
    c.imm("0c81", 1)
    c.branch(6, "recording")
    c.emit("4a80")
    c.branch(6, "cancel")
    load(c, SERIAL)
    load(c, AFTER, 1)
    c.emit("b081")
    c.branch(7, "return")
    c.imm("0681", 1)
    c.emit("b081")
    c.branch(6, "cancel")
    store(c, START_BAR)
    store(c, LAST_BAR)
    load(c, EDGE_TICK)
    store(c, START_EDGE)
    c.branch(0, "start_delay")
    c.label("recording")
    c.imm("0c80", 2)
    c.branch(6, "cancel")
    # Bound the real sample-clock duration even if the input count saturates.
    # This does not estimate tempo or schedule a stop from host elapsed time.
    c.imm("2039", TICK)
    load(c, START_TICK, 1)
    c.emit("9081")
    c.imm("0c80", MAX_CAPTURE_FRAMES)
    c.branch(2, "capacity")
    load(c, SERIAL)
    load(c, LAST_BAR, 1)
    c.emit("b081")
    c.branch(7, "return")
    c.imm("0681", 1)
    c.emit("b081")
    c.branch(6, "cancel")
    store(c, LAST_BAR)
    load(c, START_BAR, 1)
    c.emit("9081")
    load(c, DURATION_BARS, 1)
    c.emit("b081")
    c.branch(5, "return")
    c.branch(6, "cancel")
    load(c, EDGE_TICK)
    store(c, STOP_EDGE)
    c.imm("2039", TICK)
    load(c, STOP_EDGE, 1)
    c.emit("9081")
    c.imm("0c80", LATENCY)
    c.branch(2, "cancel")
    c.imm("2039", TICK)
    store(c, STOP_TICK)
    controller(c, STOP)
    inc(c, STOPS)
    setv(c, PHASE, 3)
    c.branch(0, "return")
    c.label("start_delay")
    c.imm("2039", TICK)
    load(c, START_EDGE, 1)
    c.emit("9081")
    c.imm("0c80", LATENCY)
    c.branch(2, "cancel")
    c.imm("2039", TICK)
    store(c, START_TICK)
    controller(c, START)
    inc(c, STARTS)
    setv(c, PHASE, 2)
    c.branch(0, "return")
    c.label("normalizing")
    controller(c, auto.RECORDER_STATE)
    c.imm("0c80", 3)
    c.branch(7, "return")
    c.imm("0c80", 4)
    c.branch(6, "cancel")
    n.call(c, QUEUE)
    c.branch(0, "return")
    c.label("cancel")
    n.call(c, CANCEL_FN)
    c.branch(0, "return")
    c.label("capacity")
    n.call(c, CANCEL_FN)
    load(c, PHASE)
    c.emit("4a80")
    c.branch(6, "return")
    setv(c, RESULT, CAPACITY_RESULT)
    c.label("return")
    c.emit("4cd77cfc 4fef0030 4e75")
    return c.finish(STEP)


def queue():
    c = Code()
    c.emit("4fefffb0 48d70c0c")
    controller(c, COUNT)
    c.imm("0c80", 141)
    c.branch(5, "failed")
    c.imm("0c80", MAX_CAPTURE_FRAMES)
    c.branch(2, "failed")
    c.imm("23c0", w.STATE + 28)
    for source, target in ((TRACK, 16), (KIT, 44), (EPOCH, 60), (DEST, 56)):
        load(c, source)
        c.imm("23c0", w.STATE + target)
    c.emit("7000")
    for off in (8, 24, 160):
        c.imm("23c0", w.STATE + off)
    load(c, CTRL)
    c.emit("2040 2f280010")
    n.call(c, CHANNEL, 4)
    c.emit("4a80")
    c.branch(7, "stereo")
    c.emit("7000")
    c.branch(0, "width")
    c.label("stereo")
    c.emit("7001")
    c.label("width")
    c.imm("23c0", w.STATE + 32)
    setv(c, PHASE, 4)
    c.imm("2039", TICK)
    store(c, QUEUE_TICK)
    c.imm("45f9", STATE)
    c.imm("203c", q.MANAGER)
    c.imm("223c", WORKER)
    c.emit("7400 2f4a0010 2f420014 2f400018 2f41001c")
    c.imm("223c", DONE)
    c.emit("2f4a0020 2f420024 2f400028 2f41002c")
    n.call(c, 0x40198A16)
    c.emit("2600 47ef0020 45ef0010 2f0b 2f0a")
    c.imm("4879", LABEL)
    c.emit("2f03")
    n.call(c, 0x400F0AB8, 16)
    c.emit("4a80")
    c.branch(6, "return")
    c.label("failed")
    c.emit("7000")
    c.imm("23c0", w.STATE + 12)
    store(c, PHASE)
    store(c, OWN)
    setv(c, RESULT, -3)
    c.label("return")
    c.emit("4cd70c0c 4fef0050 4e75")
    return c.finish(QUEUE)


def worker():
    c = Code()
    load(c, PHASE)
    c.imm("0c80", 4)
    c.branch(6, "bad")
    load(c, CANCEL)
    c.emit("4a80")
    c.branch(6, "bad")
    c.imm("4ef9", w.WORKER)
    c.label("bad")
    c.emit("70ff 4e75")
    return c.finish(WORKER)


def done():
    c = Code()
    c.emit("4fefffd0 48d77cfc 242f0038")  # Completion status, original SP+8.
    store(c, JOB_RESULT, 2)
    # Project reset can invalidate the shared worker ABI. Never abort through
    # its new contents or release a different job's mutation lease.
    c.imm("2039", w.STATE + 12)
    c.imm("0c80", 1)
    c.branch(6, "orphan")
    for actual, field in (
        (n.STATE, EPOCH),
        (0x80004704, KIT),
        (w.STATE + 44, KIT),
        (w.STATE + 60, EPOCH),
        (w.STATE + 56, DEST),
    ):
        c.imm("2039", actual)
        load(c, field, 1)
        c.emit("b081")
        c.branch(6, "orphan")
    c.emit("4a82")
    c.branch(6, "failed")
    n.call(c, CHECK)
    c.emit("4a80")
    c.branch(6, "abort")
    c.emit("7000")
    c.imm("23c0", w.STATE + 12)
    c.imm("2f39", w.STATE + 44)
    c.imm("2f39", w.STATE + 16)
    c.imm("2f39", w.STATE + 36)
    n.call(c, w.ASSIGN, 12)
    c.emit("4a80")
    c.branch(6, "failed")
    c.imm("2039", TICK)
    store(c, PUBLISH_TICK)
    controller(c, READY)
    inc(c, USES)
    setv(c, RESULT, 1)
    c.branch(0, "release")
    c.label("abort")
    c.imm("2f39", w.STATE + 20)
    n.call(c, w.ABORT, 4)
    c.label("failed")
    setv(c, RESULT, -4)
    c.label("release")
    c.emit("7000")
    c.imm("23c0", w.STATE + 12)
    store(c, PHASE)
    store(c, OWN)
    c.branch(0, "return")
    c.label("orphan")
    setv(c, RESULT, -5)
    setv(c, PHASE, 0)
    setv(c, OWN, 0)
    c.label("return")
    c.emit("4cd77cfc 4fef0030 4e75")
    return c.finish(DONE)


def cancel():
    c = Code()
    c.emit("4feffff0 48d70303")
    setv(c, CANCEL, 1)
    load(c, PHASE)
    c.imm("0c80", 4)
    c.branch(7, "return")  # Completion alone may abort an admitted worker.
    load(c, OWN)
    c.imm("0c80", 1)
    c.branch(6, "return")
    c.imm("2039", w.STATE + 12)
    c.imm("0c80", 1)
    c.branch(6, "release")
    c.imm("2039", n.STATE)
    load(c, EPOCH, 1)
    c.emit("b081")
    c.branch(6, "orphan")  # Do not discard another project's recorder.
    c.imm("2039", 0x80004704)
    load(c, KIT, 1)
    c.emit("b081")
    c.branch(6, "orphan")
    controller(c, auto.RECORDER_STATE)
    c.imm("0c80", 3)
    c.branch(6, "discard")
    setv(c, PHASE, 5)
    c.branch(0, "return")
    c.label("discard")
    c.emit("4a80")
    c.branch(7, "release")
    controller(c, DISCARD)
    c.label("release")
    load(c, OWN)
    c.imm("0c80", 1)
    c.branch(6, "return")
    c.imm("2039", w.STATE + 12)
    c.imm("0c80", 1)
    c.branch(6, "clear")
    c.emit("7000")
    c.imm("23c0", w.STATE + 12)
    c.label("clear")
    setv(c, OWN, 0)
    setv(c, PHASE, 0)
    setv(c, RESULT, -2)
    inc(c, CANCELS)
    c.branch(0, "return")
    c.label("orphan")
    setv(c, OWN, 0)
    setv(c, PHASE, 0)
    setv(c, RESULT, -5)
    c.label("return")
    c.emit("4cd70303 4fef0010 4e75")
    return c.finish(CANCEL_FN)


def input_event():
    c = Code()
    c.emit("4feffff0 48d70303 206f0018 2028000c")
    c.imm("0c80", 21)
    c.branch(7, "cancel")
    c.imm("0c80", 12)
    c.branch(6, "return")
    c.label("cancel")
    c.emit("20280010")
    c.imm("0280", 1)
    c.branch(7, "return")
    setv(c, CANCEL, 1)
    c.label("return")
    c.emit("4cd70303 4fef0010")
    c.imm("4ef9", perf.INPUT)
    return c.finish(INPUT)


def use_gate():
    """NORMAL USE must also respect an explicit BUF's shared mutation lease.

    Its old DEST=0 fast path otherwise bypasses the busy check, yet the worker
    dispatch still sees the BUF lease. Use the existing recorder busy exit.
    Installed only with Sketch's real ARM profile.
    """
    c = Code()
    c.imm("2039", w.STATE + 12)
    c.emit("4a80")
    c.branch(6, "busy")
    c.imm("4ef9", USE_STOCK)
    c.label("busy")
    c.emit("7601")
    c.imm("4ef9", 0x400232D2)
    return c.finish(USE_GATE)


def payload(*, arm_diagnostics=False, clock_fix=False, operation_diagnostics=False):
    contract()
    parts = {
        ARM: arm(),
        IRQ: irq(clock_fix=clock_fix),
        POLL: poll(),
        STEP: step(),
        CHECK: check(clock_fix=clock_fix),
        QUEUE: queue(),
        WORKER: worker(),
        DONE: done(),
        CANCEL_FN: cancel(),
        INPUT: input_event(),
        INIT: initialize(),
        INIT_BODY: initialize_buffers(),
        ARM_ONLY: arm_only(
            diagnostics=arm_diagnostics, operation_diagnostics=operation_diagnostics
        ),
        USE_GATE: use_gate(),
        # entry() uses absolute external targets and relative local branches.
        USE_STOCK: w.entry(),
        ARM_STOCK: ARM_BYTES + b"\x4e\xf9" + struct.pack(">I", ARM_SITE + 8),
    }
    if operation_diagnostics:
        parts[OP_SNAPSHOT] = operation_snapshot()
    ordered = sorted(parts.items())
    for (at, code), (after, _) in zip(ordered, ordered[1:], strict=False):
        require(at + len(code) <= after, f"Next-bar code overlap {at:#x}")
    require(ordered[-1][0] + len(ordered[-1][1]) <= END, "Next-bar overflow")
    return parts


def key_bridge():
    return bridge.key_hook(perf.KEY, {"input": INPUT}, perf.KEY_SITE, True)
