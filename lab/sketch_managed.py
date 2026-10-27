"""Opt-in native per-BUF settings, recorder lease and capacity/status service.

The normal sampler's settings are borrowed only during an admitted capture.
No PCM allocator, player or retirement predicate is replaced here.
"""

from lab import buf_next_bar as nb
from lab import recorder_freeze_code as n
from lab import recorder_worker_code as w
from lab import sketch as s
from lab.emit import Code
from lab.project import ROOT, read_json, require, sha256

BASE, SIZE = 0x11300000, 0x4000
STATE = BASE
INITIALIZED, PROJECT, BORROWED, POINTER, CAPTURE_BUF, FAILURE = range(0, 24, 4)
FAILURE_BUF = 24
SETTINGS, BACKUP = BASE + 0x100, BASE + 0x200
STRIDE = 32
ENSURE, INDEX = BASE + 0x1000, BASE + 0x1300
GETTERS = tuple(BASE + 0x1400 + i * 0x80 for i in range(5))
SETTERS = tuple(BASE + 0x1700 + i * 0x80 for i in range(5))
OWNER = BASE + 0x1A00
ARM, OLD_ARM, RESTORE, POLL = (BASE + x for x in (0x2000, 0x2600, 0x2A00, 0x2D00))
STATUS, CAPACITY, STATUS_TEXT, TEXTS = (
    BASE + x for x in (0x3000, 0x3400, 0x3600, 0x3800)
)
EMPTY, READY, WAIT, RECORDING, BUSY, FULL, ERROR = range(7)
LABELS = ("EMPTY", "READY", "WAIT", "REC", "BUSY", "FULL", "ERROR")


def contract():
    cfg = read_json(ROOT / "machines/sketch-managed/contract.json")
    require(cfg["status"] == "ready", "Managed Sketch contract not ready")
    require(
        sha256(ROOT / cfg["proposal"]) == cfg["proposal_sha256"],
        "Managed proposal drift",
    )
    require(
        cfg["dependencies"] == read_json(ROOT / "deps.lock.json"),
        "Managed dependency drift",
    )
    return cfg


def load(c, off, reg=0):
    c.imm(f"{0x2039 | reg << 9:04x}", STATE + off)


def store(c, off, reg=0):
    c.imm(f"{0x23C0 | reg:04x}", STATE + off)


def ensure():
    """Initialize all four preferences from the current normal sampling setup."""
    c = Code()
    c.emit("4fefffe0 48d71c1c")
    load(c, INITIALIZED)
    c.emit("4a80")
    c.branch(6, "ok")
    n.call(c, 0x401988A2)
    c.emit("4a80")
    c.branch(7, "bad")
    store(c, PROJECT)
    c.emit("2f00")
    n.call(c, 0x40041D18, 4)
    c.emit("4a80")
    c.branch(7, "bad")
    c.emit("2440")
    store(c, POINTER)
    for i, getter in enumerate(s.GETTERS):
        c.emit("2f0a")
        n.call(c, getter, 4)
        if i == 2:
            c.imm("0c80", 4)
            c.branch(5, "length_default")
            c.imm("0c80", 6)
            c.branch(3, "length_ok")
            c.label("length_default")
            c.emit("7004")
            c.label("length_ok")
        for buf in range(4):
            c.imm("23c0", SETTINGS + buf * STRIDE + i * 4)
    c.emit("7000")
    for buf in range(4):
        c.imm("23c0", SETTINGS + buf * STRIDE + 16)
    c.emit("7001")
    store(c, INITIALIZED)
    c.label("ok")
    c.emit("7000")
    c.branch(0, "return")
    c.label("bad")
    c.emit("70ff")
    c.label("return")
    c.emit("4cd71c1c 4fef0020 4e75")
    return c.finish(ENSURE)


def index():
    """Selected BUF -> preference pointer, or zero. Never clamp stale identities."""
    c = Code()
    n.call(c, ENSURE)
    c.emit("4a80")
    c.branch(6, "bad")
    s.load(c, s.BUF)
    c.emit("5380")
    c.imm("0c80", 3)
    c.branch(2, "bad")
    c.emit("e588 e588 d080")
    c.imm("0680", SETTINGS)
    c.emit("4e75")
    c.label("bad")
    c.emit("7000 4e75")
    return c.finish(INDEX)


def getter(i):
    c = Code()
    n.call(c, INDEX)
    c.emit("4a80")
    c.branch(7, "return")
    c.emit(f"2040 2028{i * 4:04x}")
    c.label("return")
    c.emit("4e75")
    return c.finish(GETTERS[i])


def setter(i):
    c = Code()
    n.call(c, INDEX)
    c.emit("4a80")
    c.branch(7, "return")
    c.emit("2040 222f0008")
    c.imm("0c81", (18, 3, 6, 1, 1)[i])
    c.branch(2, "return")
    if i == 2:
        c.imm("0c81", 4)
        c.branch(5, "return")
    c.emit(f"2141{i * 4:04x}")
    load(c, FAILURE_BUF)
    s.load(c, s.BUF, 1)
    c.emit("b081")
    c.branch(6, "return")
    c.emit("7000")
    store(c, FAILURE)
    c.label("return")
    c.emit("4e75")
    return c.finish(SETTERS[i])


def capacity():
    """Count vacant generation seats; a pinned or quarantined seat is occupied."""
    c = Code()
    c.imm("41f9", n.GEN)
    c.emit("2f02 7000 7208")
    c.label("next")
    c.emit("2410 4a82")
    c.branch(6, "occupied")
    c.emit("5280")
    c.label("occupied")
    c.emit("41e80040 5381")
    c.branch(6, "next")
    c.emit("241f 4e75")
    return c.finish(CAPACITY)


def owner():
    """Authenticate both project and settings wrapper before borrowing/restoring."""
    c = Code()
    n.call(c, 0x401988A2)
    load(c, PROJECT, 1)
    c.emit("b081")
    c.branch(6, "bad")
    c.emit("4a80")
    c.branch(7, "bad")
    c.emit("2f00")
    n.call(c, 0x40041D18, 4)
    load(c, POINTER, 1)
    c.emit("b081")
    c.branch(6, "bad")
    c.emit("4a80")
    c.branch(7, "bad")
    c.emit("7000 4e75")
    c.label("bad")
    c.emit("70ff 4e75")
    return c.finish(OWNER)


def arm():
    c = Code()
    c.emit("4fefffe0 48d71c1c")
    # The existing global chord also stops a manual take. Its owner decides
    # whether this is a stop, cancel or busy event; never borrow settings twice.
    nb.load(c, nb.PHASE)
    c.emit("4a80")
    c.branch(7, "admission")
    n.call(c, OLD_ARM)
    c.branch(0, "return")
    c.label("admission")
    for at in (STATE + BORROWED, w.STATE + 12, nb.STATE + nb.PHASE):
        c.imm("2039", at)
        c.emit("4a80")
        c.branch(6, "busy")
    n.call(c, 0x4019988A)
    c.emit("2f00")
    n.call(c, 0x40015F6C, 4)
    c.emit("4a80")
    c.branch(6, "busy")
    n.call(c, ENSURE)
    c.emit("4a80")
    c.branch(6, "bad")
    n.call(c, OWNER)
    c.emit("4a80")
    c.branch(6, "bad")
    n.call(c, CAPACITY)
    c.emit("4a80")
    c.branch(7, "full")
    s.load(c, s.LATCH)
    c.emit("5380")
    c.imm("0c80", 3)
    c.branch(2, "bad")
    c.emit("e588 e588 d080")
    c.imm("47f9", SETTINGS)
    c.emit("d7c0")
    load(c, POINTER)
    c.emit("2440")
    # Snapshot normal values before changing any of them.
    for i, getter_at in enumerate(s.GETTERS):
        c.emit("2f0a")
        n.call(c, getter_at, 4)
        c.imm("23c0", BACKUP + i * 4)
    s.load(c, s.START_MODE)
    c.imm("23c0", BACKUP + 16)
    s.load(c, s.LATCH)
    store(c, CAPTURE_BUF)
    store(c, FAILURE_BUF)
    c.emit("7001")
    store(c, BORROWED)
    for i, setter_at in enumerate(s.SETTERS):
        c.emit(f"2f2b{i * 4:04x} 2f0a")
        n.call(c, setter_at, 8)
    c.emit("202b0010")
    s.store(c, s.START_MODE)
    c.emit("7000")
    store(c, FAILURE)
    n.call(c, OLD_ARM)
    s.load(c, s.ARM_RESULT)
    c.emit("4a80")
    c.branch(7, "return")
    c.emit("7001")
    store(c, FAILURE)
    n.call(c, RESTORE)
    c.branch(0, "return")
    for label, result, action, failure in (
        ("busy", nb.ARM_BUSY, 9, 0),
        ("full", nb.CAPACITY_RESULT, s.ARM_CAPACITY, 2),
        ("bad", nb.ARM_REFUSED, 10, 1),
    ):
        c.label(label)
        c.imm("203c", result)
        s.store(c, s.ARM_RESULT)
        s.setv(c, s.ACTION, action)
        c.imm("203c", failure)
        store(c, FAILURE)
        s.load(c, s.LATCH)
        store(c, FAILURE_BUF)
        c.branch(0, "return")
    c.label("return")
    c.emit("4cd71c1c 4fef0020 4e75")
    return c.finish(ARM)


def restore():
    c = Code()
    c.emit("4feffff0 48d70c0c")
    load(c, BORROWED)
    c.emit("4a80")
    c.branch(7, "done")
    for at in (nb.STATE + nb.PHASE, w.STATE + 12):
        c.imm("2039", at)
        c.emit("4a80")
        c.branch(6, "done")
    n.call(c, OWNER)
    c.emit("4a80")
    c.branch(6, "stale")
    load(c, POINTER)
    c.emit("2440")
    for i, setter_at in enumerate(s.SETTERS):
        c.imm("2039", BACKUP + i * 4)
        c.emit("2f00 2f0a")
        n.call(c, setter_at, 8)
    c.imm("2039", BACKUP + 16)
    s.store(c, s.START_MODE)
    # Completion may fail after admission; keep that visible on its own BUF.
    nb.load(c, nb.RESULT)
    c.imm("0c80", 1)
    c.branch(7, "released")
    c.imm("0c80", -2)  # Explicit cancellation is not a damaged take.
    c.branch(7, "released")
    c.emit("4a80")
    c.branch(7, "released")  # Refused admission already recorded its error.
    c.emit("7001")
    store(c, FAILURE)
    load(c, CAPTURE_BUF)
    store(c, FAILURE_BUF)
    c.label("released")
    c.emit("7000")
    store(c, BORROWED)
    c.branch(0, "done")
    c.label("stale")
    # Never write a previous project's settings through a dangling pointer.
    c.emit("7001")
    store(c, FAILURE)
    load(c, CAPTURE_BUF)
    store(c, FAILURE_BUF)
    c.label("done")
    c.emit("4cd70c0c 4fef0010 4e75")
    return c.finish(RESTORE)


def poll(*, buf_loading=False):
    from lab import sketchbook_ui as ui

    c = Code()
    c.emit("4feffff0 48d70303")
    if buf_loading:
        # The ordinary recorder may remain at NORMAL while a pending SRC list
        # is open. Retry through the existing whole-batch gate without reopening.
        n.call(c, nb.INIT_BODY)
    n.call(c, RESTORE)
    c.emit("4cd70303 4fef0010")
    c.imm("4ef9", ui.POLL)
    return c.finish(POLL)


def status():
    c = Code()
    c.emit("4feffff0 48d70c0c")
    nb.load(c, nb.PHASE)
    c.emit("4a80")
    c.branch(7, "idle")
    c.emit("2400")
    s.load(c, s.BUF)
    nb.load(c, nb.DEST, 1)
    c.emit("b081")
    c.branch(6, "idle")
    c.imm("0c82", 2)
    c.branch(7, "rec")
    c.imm("0c82", 1)
    c.branch(7, "wait")
    c.imm("0c82", 6)
    c.branch(7, "wait")
    c.branch(0, "busy")
    c.label("idle")
    c.imm("2039", w.STATE + 12)
    c.emit("4a80")
    c.branch(6, "busy")
    load(c, FAILURE_BUF)
    s.load(c, s.BUF, 1)
    c.emit("b081")
    c.branch(6, "capacity")
    load(c, FAILURE)
    c.imm("0c80", 1)
    c.branch(7, "error")
    c.label("capacity")
    n.call(c, CAPACITY)
    c.emit("4a80")
    c.branch(7, "full")
    s.load(c, s.BUF)
    c.emit("2f00")
    n.call(c, s.READY, 4)
    c.emit("4a80")
    c.branch(6, "ready")
    c.branch(0, "empty")
    for label, value in (
        ("empty", EMPTY),
        ("ready", READY),
        ("wait", WAIT),
        ("rec", RECORDING),
        ("busy", BUSY),
        ("full", FULL),
        ("error", ERROR),
    ):
        c.label(label)
        c.imm("203c", value)
        c.branch(0, "return")
    c.label("return")
    c.emit("4cd70c0c 4fef0010 4e75")
    return c.finish(STATUS)


def status_text(*, buf_loading=False):
    c = Code()
    if buf_loading:
        from lab import buf_loading as loading

        nb.load(c, nb.PHASE)
        c.emit("4a80")
        c.branch(7, "availability")
        c.imm("0c80", 6)  # A completed take waiting on project loading.
        c.branch(6, "ordinary")
        c.imm("203c", loading.TEXTS)
        c.emit("4e75")
        c.label("availability")
        n.call(c, loading.AVAILABILITY)
        c.emit("4a80")
        c.branch(7, "ordinary")
        c.emit("5380 e588 e588")
        c.imm("0680", loading.TEXTS)
        c.emit("4e75")
        c.label("ordinary")
    n.call(c, STATUS)
    c.emit("e588 e588")
    c.imm("0680", TEXTS)
    c.emit("4e75")
    return c.finish(STATUS_TEXT)


def payload():
    contract()
    return {
        ENSURE: ensure(),
        INDEX: index(),
        ARM: arm(),
        RESTORE: restore(),
        POLL: poll(),
        STATUS: status(),
        STATUS_TEXT: status_text(),
        CAPACITY: capacity(),
        OWNER: owner(),
        **{at: getter(i) for i, at in enumerate(GETTERS)},
        **{at: setter(i) for i, at in enumerate(SETTERS)},
    }
