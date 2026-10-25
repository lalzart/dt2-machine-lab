"""Small native OS 1.16 Sketch view with opt-in ARM/FREEZE, emulator only.

One volatile UI selection survives view destruction; no recorder DEST writes,
assignment, persistence or SamplerView clone. Default shortcuts stay dry.
"""

import hashlib
import struct

from lab import arp_firmware as abi
from lab import buf_freeze as bf
from lab import buf_next_bar as nb
from lab import buf_performance as perf
from lab import recorder_freeze_code as frozen
from lab import recorder_freeze_worker_code as freeze_jobs
from lab import recorder_native_retirement as retirement
from lab import recorder_worker_code as worker
from lab.dt2_116 import STOCK_SHA
from lab.emit import Code
from lab.project import require

BASE, END = 0x11100000, 0x11108000  # Emulator scratch; no target reservation.
STATE = BASE
BUF, VIEW, OWN, FUNC_OWN, LATCH, KIT, PROJECT, DEST, SEEN, ACTION = range(0, 40, 4)
ARMS, FREEZES, PAGE, DRAWS, FIRST = range(40, 60, 4)
EPOCH = 60
LAST_PAINT, UPDATES = 64, 68
ARM_RESULT = 72
FREEZE_RESULT, FREEZE_DONE = 76, 80
ARM_COUNT, ARM_EPOCH, ARM_KIT, ARM_PROJECT, ARM_BUF, ARM_POOL = range(84, 108, 4)
ARM_DIAG, ARM_DIAG_VALUE = 108, 112  # Snapshot the last physical ARM request.
OP_CONTEXT = 116
OP_DIAG = BASE + 0x5400
OP_DIAGNOSTICS = ("LOAD", "UNLOAD", "CLEAR")
ARM_WAITING = 8
ARM_RECORDING, ARM_PROCESSING, ARM_LOADING, ARM_CANCELLING = range(20, 24)
ARM_READY, ARM_CANCELLED, ARM_FAILED, ARM_STALE = range(24, 28)
ARM_CAPACITY = 28
UPDATE = BASE + 0x4500
ARM_SUBMIT = BASE + 0x4800
FREEZE_SUBMIT, FREEZE_FEEDBACK = BASE + 0x4A00, BASE + 0x4D00
ARM_FEEDBACK = BASE + 0x4E00
PANEL_TICK, REFRESH_TICKS = 0x47DDEC1C, 12
INPUT, KEY, MAIN_KEY, VIEW_KEY = (
    BASE + 0x1000,
    BASE + 0x1800,
    BASE + 0x1900,
    BASE + 0x1A00,
)
OPEN, DISPOSE, DTOR, ROTATE = BASE + 0x2000, BASE + 0x2400, BASE + 0x2500, BASE + 0x2800
DRAW, ROUTE, ROUTE_STOCK, READY = (
    BASE + 0x3000,
    BASE + 0x4000,
    BASE + 0x4200,
    BASE + 0x4400,
)
VTABLE, SHARED, TEXTS, STRINGS, LINE = (
    BASE + 0x5008,
    BASE + 0x5100,
    BASE + 0x5200,
    BASE + 0x5600,
    BASE + 0x7000,
)
MAIN_SITE, ROUTE_SITE = 0x400649C4, 0x4011C4BC
MAIN_BYTES = bytes.fromhex("4e56ff9848d73cfc")
# Filled from authenticated stock, then independently checked by installation.
OBJECT_SIZE, SCALER, SETTINGS = 0x150, 0x50, 0x14C
FONT, TEXT, PRINT = 0x44D2E70C, 0x40113AE8, 0x40000E82
CLEAR = BASE + 0x4C00
GETTERS = (0x4004CC72, 0x4004CCA2, 0x4004CC42, 0x4004CD02)
SETTERS = (0x4004CFD6, 0x4004D030, 0x4004CF7C, 0x4004D0D2)
LABELS = {
    "title": "SKETCH       A:BUF %u",
    "source": "B:SRC %s%s  C:%s",
    "length": "D:LEN %s E:MON %s",
    "status": "REC:%s BUF:%s",
    "pair": "%u:%s  %u:%s",
    "hint": "DRY RUN HOLD:FREEZE",
    "arm": "WOULD ARM BUF %u",
    "freeze": "WOULD FREEZE BUF %u",
    "busy": "DRY: BUSY / NO JOB",
    "empty": "DRY: EMPTY / NO JOB",
    "unsupported": "DRY: LEN UNSUPPORTED",
    "cancel": "DRY: CYCLE CANCELLED",
    "hint_live": "FUNC:ARM HOLD:DRY",
    "hint_both": "FUNC:ARM HOLD:FREEZE",
    "hint_freeze": "FUNC:DRY HOLD:FREEZE",
    "freeze_queued": "FREEZE QUEUED",
    "freeze_ready": "FREEZE READY / YES",
    "freeze_busy": "FREEZE: BUSY / NO JOB",
    "freeze_empty": "FREEZE: EMPTY / NO JOB",
    "freeze_full": "FREEZE: LIST FULL",
    "freeze_refused": "FREEZE: REFUSED",
    "freeze_failed": "FREEZE: FAILED",
    "freeze_stale": "FREEZE: STALE",
    "arm_ok": "BUF %u: WAIT BAR",
    "arm_busy": "ARM: BUSY / NO JOB",
    "arm_refused": "ARM: REFUSED",
    "arm_length": "ARM: LEN 16/32/64",
    "arm_recording": "BUF %u: RECORDING",
    "arm_processing": "BUF %u: PROCESSING",
    "arm_loading": "BUF %u: LOADING",
    "arm_cancelling": "BUF %u: CANCELLING",
    "arm_ready": "BUF %u: READY",
    "arm_cancelled": "BUF %u: CANCELLED",
    "arm_failed": "BUF %u: FAILED",
    "arm_stale": "BUF %u: STALE",
    "arm_capacity": "BUF %u: TOO LONG",
    "nav": "YES:TAKES NO:BACK",
    "takes": "FROZEN TAKES %u-%u",
    "take": "%03u %s",
    "none": "NO READY TAKES",
    "takes_nav": "UP/DN:PAGE YES:BUF",
    "empty_buf": "EMPTY",
    "ready_buf": "READY",
    "unavailable": "N/A",
    "off": "OFF",
    "on": "ON",
    "ready": "READY",
    "armed": "ARMED",
    "recording": "RECORD",
    "processing": "PROC",
    "trim": "TRIM",
    "idle": "IDLE",
    "commit": "COMMIT",
    "failed": "REFUSED",
    **{
        f"len{i}": str(1 << i) + ("!" if i not in nb.RLEN_BARS else "")
        for i in range(8)
    },
    "len8": "MAX!",
}


def call(c, at, pops=0):
    c.imm("4eb9", at)
    if pops:
        c.emit(f"4fef{pops:04x}")


def load(c, field, reg=0):
    c.imm(f"{0x2039 | reg << 9:04x}", STATE + field)


def store(c, field, reg=0):
    c.imm(f"{0x23C0 | reg:04x}", STATE + field)


def setv(c, field, value):
    c.imm("203c", value)
    store(c, field)


def bridge(at, fallback):
    c = Code()
    c.emit(abi.PRESAVE + " 2f2f002c 2f2f002c")
    call(c, INPUT, 8)
    c.emit("4a80")
    c.branch(7, "stock")
    c.emit("7001 " + abi.RESTORE + " 4e75")
    c.label("stock")
    c.emit(abi.RESTORE)
    c.imm("4ef9", fallback)
    return c.finish(at)


def input_event(*, arm_enabled=False, freeze_enabled=False):
    c = Code()
    c.emit(abi.PRESAVE + " 246f0028 266f002c 242b000c 262b0010")
    setv(c, SEEN, 1)
    # Context is latched at press. Never infer destination from the track.
    load(c, OWN)
    c.imm("0c80", 1)
    c.branch(6, "key")  # Submitted actions no longer belong to gesture context.
    for at, field in (
        (0x80004704, KIT),
        (0x44F370A0, PROJECT),
        (worker.DEST, DEST),
        (frozen.STATE, EPOCH),
        (STATE + BUF, LATCH),
    ):
        c.imm("2039", at)
        load(c, field, 1)
        c.emit("b081")
        c.branch(6, "cancel_context")
    c.branch(0, "key")
    c.label("cancel_context")
    setv(c, OWN, 4)
    setv(c, ACTION, 7)
    c.label("key")
    c.imm("0c82", 24)
    c.branch(7, "song")
    c.imm("0c82", 17)
    c.branch(7, "func")
    load(c, OWN)
    c.emit("4a80")
    c.branch(7, "view_keys")
    c.emit("2003")
    c.imm("0280", 1)
    c.branch(7, "view_keys")
    setv(c, OWN, 4)
    setv(c, ACTION, 7)
    # Suppress conflicting SONG+arrow/trig gestures in the opt-in surface.
    for key in (8, 9, 11, 14, *range(25, 41)):
        c.imm("0c82", key)
        c.branch(7, "consume")
    c.label("view_keys")
    load(c, VIEW)
    c.emit("220a b081")
    c.branch(6, "no")
    c.imm("0c82", 12)
    c.branch(7, "back")
    c.imm("0c82", 50)
    c.branch(7, "sampling")
    for key in (10, 11, 14):
        c.imm("0c82", key)
        c.branch(7, "page_key")
    # STOP and all performance/cancellation keys continue through controller.
    c.branch(0, "no")
    c.label("sampling")
    c.emit("2f0a")
    call(c, 0x4011AEEA, 4)
    c.branch(0, "no")
    c.label("back")
    c.emit("2f0a")
    call(c, 0x4011AEEA, 4)
    c.branch(0, "no")  # NO must still reach existing cancellation owners.
    c.label("page_key")
    c.emit("2003")
    c.imm("0280", 9)
    c.imm("0c80", 1)
    c.branch(6, "consume")
    c.imm("0c82", 10)
    c.branch(6, "scroll")
    load(c, PAGE)
    c.emit("4a80")
    c.branch(7, "page_on")
    c.emit("7000")
    c.branch(0, "page_set")
    c.label("page_on")
    c.emit("7001")
    c.label("page_set")
    store(c, PAGE)
    c.branch(0, "invalidate")
    c.label("scroll")
    load(c, PAGE)
    c.emit("4a80")
    c.branch(7, "consume")
    load(c, FIRST)
    c.emit("4a80")
    c.branch(7, "first_on")
    c.emit("7000")
    c.branch(0, "first_set")
    c.label("first_on")
    c.emit("7004")
    c.label("first_set")
    store(c, FIRST)
    c.branch(0, "invalidate")
    c.label("func")
    load(c, FUNC_OWN)
    c.emit("4a80")
    c.branch(7, "func_new")
    c.emit("2003")
    c.imm("0280", 1)
    c.branch(6, "consume")
    setv(c, FUNC_OWN, 0)
    c.branch(0, "consume")
    c.label("func_new")
    load(c, OWN)
    c.imm("0c80", 1)
    c.branch(6, "no")
    c.emit("2003")
    c.imm("0280", 9)
    c.imm("0c80", 1)
    c.branch(6, "no")
    c.branch(0, "arm")
    c.label("song")
    load(c, OWN)
    c.emit("4a80")
    c.branch(6, "owned")
    c.emit("2003")
    c.imm("0280", 9)
    c.imm("0c80", 1)
    c.branch(6, "no")
    setv(c, OWN, 1)
    for at, field in (
        (STATE + BUF, LATCH),
        (0x80004704, KIT),
        (0x44F370A0, PROJECT),
        (worker.DEST, DEST),
        (frozen.STATE, EPOCH),
    ):
        c.imm("2039", at)
        store(c, field)
    c.imm("4879", 17)
    call(c, 0x4011DE70, 4)
    c.imm("0280", 255)
    c.emit("4a80")
    c.branch(6, "arm")
    c.branch(0, "consume")
    c.label("owned")
    c.emit("2003")
    c.imm("0280", 1)
    c.branch(7, "release")
    load(c, OWN)
    c.imm("0c80", 1)
    c.branch(6, "consume")
    c.emit("2003")
    c.imm("0280", 0x29)
    c.imm("0c80", 0x29)
    c.branch(6, "consume")
    setv(c, OWN, 3)
    load(c, FREEZES)
    c.emit("5280")
    store(c, FREEZES)
    if freeze_enabled:
        call(c, FREEZE_SUBMIT)
        c.branch(0, "invalidate")
    setv(c, ACTION, 2)
    call(c, 0x4019988A)
    c.emit("2f00")
    call(c, 0x40015F6C, 4)
    c.emit("4a80")
    c.branch(6, "busy")
    load(c, LATCH)
    c.emit("2f00")
    call(c, READY, 4)
    c.emit("4a80")
    c.branch(6, "invalidate")
    setv(c, ACTION, 4)
    c.branch(0, "invalidate")
    c.label("arm")
    setv(c, OWN, 2)
    setv(c, FUNC_OWN, 1)
    load(c, ARMS)
    c.emit("5280")
    store(c, ARMS)
    if arm_enabled:
        call(c, ARM_SUBMIT)
        c.branch(0, "invalidate")
    # Retain the original dry surface as an explicit negative-control profile.
    setv(c, ACTION, 1)
    call(c, 0x4019988A)
    c.emit("2f00")
    call(c, 0x40015F6C, 4)
    c.emit("4a80")
    c.branch(6, "busy")
    call(c, 0x401988A2)
    c.emit("2f00")
    call(c, 0x40041D18, 4)
    c.emit("2f00")
    call(c, GETTERS[2], 4)
    for raw in nb.RLEN_BARS:
        c.imm("0c80", raw)
        c.branch(7, "invalidate")
    setv(c, ACTION, 5)
    c.branch(0, "invalidate")
    c.label("busy")
    setv(c, ACTION, 3)
    c.branch(0, "invalidate")
    c.label("release")
    load(c, OWN, 2)
    setv(c, OWN, 0)
    c.imm("0c82", 1)
    c.branch(6, "consume")
    load(c, VIEW)
    c.emit("4a80")
    c.branch(7, "open")
    c.emit("2f00")
    call(c, 0x4011AEEA, 4)
    c.branch(0, "consume")
    c.label("open")
    c.emit("2f0a")
    call(c, OPEN, 4)
    c.branch(0, "consume")
    c.label("invalidate")
    load(c, VIEW)
    c.emit("4a80")
    c.branch(7, "consume")
    c.emit("2f00")
    call(c, 0x4011AE46, 4)
    c.label("consume")
    # Returning consumed lets ViewController own delivery. The held-cycle
    # helper clears native repeat/hold tracking, so do not call it here.
    c.emit("7001")
    c.branch(0, "done")
    c.label("no")
    c.emit("7000")
    c.label("done")
    c.emit(abi.RESTORE + " 4e75")
    return c.finish(INPUT)


def open_view():
    c = Code()
    c.emit("4fefffe0 48d70c0c 246f0024")
    c.imm("4879", OBJECT_SIZE + 16)
    call(c, 0x4011E8F0, 4)
    c.emit("4a80")
    c.branch(7, "done")
    c.emit("2640")  # A3=control block, A0=view; construct only native base.
    c.imm("203c", SHARED)
    c.emit("2680 7001 27400004 27400008 41eb0010 2748000c")
    c.imm("4879", STRINGS)
    c.emit("2f08")
    call(c, 0x4011AD8E, 8)
    c.emit("41eb0010")
    c.imm("203c", VTABLE)
    c.emit("2080")
    c.imm("203c", SHARED + 0x58)
    c.emit("21400004 2008")
    store(c, VIEW)
    c.emit("2f480018 2f4b001c 41e80050 2f08")
    call(c, 0x40111888, 4)
    call(c, 0x401988A2)
    c.emit("2f00")
    call(c, 0x40041D18, 4)
    c.emit("206b000c 2140014c")
    setv(c, PAGE, 0)
    c.emit("7000 2f00 41ef001c 2f08 2f0a")
    call(c, 0x4011AF4A, 12)
    c.emit("41ef001c 2f08")
    call(c, 0x40197A4A, 4)
    c.label("done")
    c.emit("4cd70c0c 4fef0020 4e75")
    return c.finish(OPEN)


def destructor():
    c = Code()
    # Last raw pointer is weak observation only; controller owns lifetime.
    setv(c, VIEW, 0)
    c.emit("2f2f0004 206f0008 41e80050 2250 2f08 2251 4e91 588f")
    call(c, 0x4011AFE4, 4)
    c.emit("4e75")
    return c.finish(DTOR)


def dispose():
    c = Code()
    c.emit("206f0004 2f28000c")
    call(c, DTOR, 4)
    c.emit("4e75")
    return c.finish(DISPOSE)


def rotation():
    c = Code()
    c.emit(abi.PRESAVE + " 246f0028 266f002c")
    # Predicate + original scaler preserve native acceleration/filtering.
    for i in range(5):
        c.imm("4879", i)
        c.emit("2f0b")
        call(c, 0x40111732, 8)
        c.imm("0280", 255)
        c.emit("4a80")
        c.branch(6, f"encoder{i}")
    c.branch(0, "done")
    for i in range(5):
        c.label(f"encoder{i}")
        c.imm("4879", 0x44D2E61C)
        c.emit("2f0b 41ea0050 2f08")
        call(c, 0x40111B62, 12)
        c.emit("4a80")
        c.branch(12, f"scaled{i}")
        c.imm("0680", 255)
        c.label(f"scaled{i}")
        c.emit("e080 2400 4a80")
        c.branch(7, "done")
        if i == 0:
            load(c, BUF)
            c.emit("d082")
            clamp(c, 1, 4, "buf")
            store(c, BUF)
        else:
            # Keep the recorder's existing edit gate; active capture owns settings.
            call(c, 0x4019988A)
            c.emit("2f00")
            call(c, 0x40015F6C, 4)
            c.imm("0c80", 1)
            c.branch(14, "done")
            if i == 4:
                c.emit("2f2a014c")
                call(c, GETTERS[0], 4)
                c.imm("0c80", 18)
                c.branch(6, "done")
            c.emit("2f2a014c")
            call(c, GETTERS[i - 1], 4)
            c.emit("d082")
            clamp(c, 0, (18, 3, 8, 1)[i - 1], f"setting{i}")
            c.emit("2f00 2f2a014c")
            call(c, SETTERS[i - 1], 8)
        setv(c, ACTION, 0)
        c.emit("2f0a")
        call(c, 0x4011AE46, 4)
        c.branch(0, "done")
    c.label("done")
    c.emit("7001 " + abi.RESTORE + " 4e75")
    return c.finish(ROTATE)


def clamp(c, low, high, prefix):
    c.imm("0c80", low)
    c.branch(12, prefix + "low")
    c.imm("203c", low)
    c.label(prefix + "low")
    c.imm("0c80", high)
    c.branch(15, prefix + "high")
    c.imm("203c", high)
    c.label(prefix + "high")


def ready():
    c = Code()
    c.emit("202f0004")
    c.imm("0680", -1)
    c.imm("0c80", 3)
    c.branch(2, "bad")
    c.emit("d080 d080")
    c.imm("41f9", worker.STATE + 96)
    c.emit("d1c0 2010")
    c.emit("4a80")
    c.branch(7, "bad")
    c.imm("0c80", 1023)
    c.branch(2, "bad")
    c.emit("d080 d080 d080 d080")
    c.imm("41f9", 0x405B1368)
    c.emit("d1c0 20280008 4a80")
    c.branch(7, "bad")
    c.emit("2028000c 4e75")
    c.label("bad")
    c.emit("7000 4e75")
    return c.finish(READY)


def route(prefix):
    c = Code()
    c.emit(abi.PRESAVE)
    setv(c, SEEN, 0)
    c.emit("2f2f002c 2f2f002c")
    call(c, ROUTE_STOCK, 8)
    c.emit("2400")
    load(c, SEEN)
    c.emit("4a80")
    c.branch(6, "done")
    load(c, OWN)
    c.emit("4a80")
    c.branch(7, "foreign_release")
    setv(c, OWN, 4)
    setv(c, ACTION, 7)
    c.label("foreign_release")
    # The foreign modal already handled the event. Retire only our own
    # latches when it consumes an owned release, without stealing that key.
    c.emit("206f002c 20280010")
    c.imm("0280", 1)
    c.branch(6, "done")
    c.emit("2028000c")
    c.imm("0c80", 24)
    c.branch(6, "foreign_func")
    setv(c, OWN, 0)
    c.branch(0, "done")
    c.label("foreign_func")
    c.imm("0c80", 17)
    c.branch(6, "done")
    setv(c, FUNC_OWN, 0)
    c.label("done")
    c.emit("2002 " + abi.RESTORE + " 4e75")
    trampoline = (
        prefix + bytes.fromhex("4ef9") + struct.pack(">I", ROUTE_SITE + len(prefix))
    )
    return c.finish(ROUTE), trampoline


def update(*, arm_enabled=False):
    """Native View update callback, throttled status refresh without jobs.

    Invalidating inside draw is cleared by ViewController after that draw.
    Use the same periodic virtual callback as SamplerView, with no waveform
    requests or capture actions, and yield to normal modal composition.
    """
    c = Code()
    c.emit(abi.PRESAVE + " 246f0028 7000 102a0030 4a80")
    c.branch(6, "done")
    c.imm("2039", PANEL_TICK)
    c.emit("2400")
    load(c, LAST_PAINT, 1)
    c.emit("9081")
    c.imm("0c80", REFRESH_TICKS)
    c.branch(5, "done")
    store(c, LAST_PAINT, 2)
    load(c, UPDATES)
    c.emit("5280")
    store(c, UPDATES)
    if arm_enabled:
        call(c, ARM_FEEDBACK)
    call(c, FREEZE_FEEDBACK)
    c.emit("2f0a")
    call(c, 0x4011AE46, 4)
    c.label("done")
    c.emit("7000 " + abi.RESTORE + " 4e75")
    return c.finish(UPDATE)


def submit_arm(*, diagnostics=False, clock_fix=False, operation_diagnostics=False):
    """Native GUI action; request the latched BUF without forging panel input."""
    c = Code()
    load(c, LATCH)
    c.emit("2f00")
    call(c, 0x4019988A)
    c.emit("2f00")
    call(c, nb.ARM_ONLY, 8)
    store(c, ARM_RESULT)
    if diagnostics:
        for source, target in (
            (nb.ARM_DIAG, ARM_DIAG),
            (nb.ARM_DIAG_VALUE, ARM_DIAG_VALUE),
        ):
            c.imm("2239", nb.STATE + source)
            store(c, target, 1)
        if clock_fix:
            load(c, ARM_DIAG, 1)
            c.imm("0c81", 11)
            c.branch(6, "diagnosis_done")
            c.imm("2239", nb.STATE + nb.CLOCK_DIAG)
            c.imm("0681", len(nb.ARM_DIAGNOSTICS) + 1)
            store(c, ARM_DIAG, 1)
            c.imm("2239", nb.STATE + nb.CLOCK_DIAG_VALUE)
            store(c, ARM_DIAG_VALUE, 1)
            c.label("diagnosis_done")
        if operation_diagnostics:
            call(c, OP_DIAG)
    c.emit("4a80")
    c.branch(7, "accepted")
    c.imm("0c80", nb.ARM_BUSY)
    c.branch(7, "busy")
    c.imm("0c80", nb.ARM_LENGTH)
    c.branch(7, "length")
    setv(c, ACTION, 10)
    c.branch(0, "return")
    c.label("accepted")
    # Observe this admitted transaction only. No ownership or recorder writes.
    for actual, field in (
        (nb.STATE + nb.ARMS, ARM_COUNT),
        (nb.STATE + nb.EPOCH, ARM_EPOCH),
        (nb.STATE + nb.KIT, ARM_KIT),
        (0x44F370A0, ARM_PROJECT),
        (nb.STATE + nb.DEST, ARM_BUF),
        (nb.STATE + nb.POOL, ARM_POOL),
    ):
        c.imm("2039", actual)
        store(c, field)
    setv(c, ACTION, ARM_WAITING)
    c.branch(0, "return")
    c.label("busy")
    setv(c, ACTION, 9)
    c.branch(0, "return")
    c.label("length")
    setv(c, ACTION, 11)
    c.label("return")
    c.emit("4e75")
    return c.finish(ARM_SUBMIT)


def operation_diagnosis():
    """Render only a still-active outer operation from the atomic ARM snapshot."""
    c = Code()
    c.emit("4feffff0 48d70003")
    load(c, ARM_DIAG, 1)
    c.imm("0c81", 4)
    c.branch(6, "return")
    for index, _field in enumerate(freeze_jobs.OP_FIELDS):
        c.imm("2239", nb.STATE + nb.OP_CONTEXT + index * 4)
        store(c, OP_CONTEXT + index * 4, 1)
    load(c, OP_CONTEXT + freeze_jobs.OP_RETURNED - freeze_jobs.OP_SITE, 1)
    c.emit("4a81")
    c.branch(6, "return")
    load(c, OP_CONTEXT, 1)
    for index in range(3):
        for base in (retirement.GUARDS, freeze_jobs.GUARDS):
            c.imm("0c81", base + index * 256 + 14)
            c.branch(7, f"operation{index}")
    c.branch(0, "return")
    for index in range(3):
        c.label(f"operation{index}")
        arg = freeze_jobs.OP_ARG2 if index == 0 else freeze_jobs.OP_ARG1
        load(c, OP_CONTEXT + arg - freeze_jobs.OP_SITE, 1)
        store(c, ARM_DIAG_VALUE, 1)
        c.imm("223c", len(nb.ARM_DIAGNOSTICS) + index + 1)
        store(c, ARM_DIAG, 1)
        c.branch(0, "return")
    c.label("return")
    c.emit("4cd70003 4fef0010 4e75")
    return c.finish(OP_DIAG)


def submit_freeze():
    c = Code()
    # Completion count distinguishes this request from the previous result.
    c.imm("2039", freeze_jobs.STATE + 32)
    store(c, FREEZE_DONE)
    load(c, LATCH)
    c.emit("2f00")
    call(c, bf.SUBMIT, 4)
    store(c, FREEZE_RESULT)
    c.emit("4a80")
    c.branch(7, "accepted")
    for value, action in ((-7, 14), (-2, 15), (-5, 16), (-6, 18)):
        c.imm("0c80", value)
        c.branch(7, f"action{action}")
    setv(c, ACTION, 17)
    c.branch(0, "return")
    c.label("accepted")
    setv(c, ACTION, 12)
    c.branch(0, "return")
    for action in (14, 15, 16, 18):
        c.label(f"action{action}")
        setv(c, ACTION, action)
        c.branch(0, "return")
    c.label("return")
    c.emit("4e75")
    return c.finish(FREEZE_SUBMIT)


def freeze_feedback():
    c = Code()
    load(c, ACTION)
    c.imm("0c80", 12)
    c.branch(6, "return")
    c.imm("2039", freeze_jobs.STATE + 32)
    load(c, FREEZE_DONE, 1)
    c.emit("b081")
    c.branch(7, "return")
    c.imm("2039", freeze_jobs.STATE + 12)
    store(c, FREEZE_RESULT)
    c.emit("4a80")
    c.branch(10, "ready")
    c.imm("0c80", -3)
    c.branch(7, "stale")
    setv(c, ACTION, 18)
    c.branch(0, "return")
    c.label("ready")
    setv(c, ACTION, 13)
    c.branch(0, "return")
    c.label("stale")
    setv(c, ACTION, 19)
    c.label("return")
    c.emit("4e75")
    return c.finish(FREEZE_FEEDBACK)


def arm_feedback():
    """Read-only lifecycle feedback for the last admitted Sketch ARM.

    A newer action owns its own message. Never infer completion from an old
    result, a replacement transaction or a different project's recorder.
    """
    c = Code()
    load(c, ACTION)
    for action in (ARM_WAITING, *range(ARM_RECORDING, ARM_CANCELLING + 1)):
        c.imm("0c80", action)
        c.branch(7, "observe")
    c.branch(0, "return")
    c.label("observe")
    for actual, field in (
        (nb.STATE + nb.ARMS, ARM_COUNT),
        (frozen.STATE, ARM_EPOCH),
        (0x80004704, ARM_KIT),
        (0x44F370A0, ARM_PROJECT),
        (nb.STATE + nb.DEST, ARM_BUF),
        (worker.STATE + 68, ARM_POOL),
    ):
        c.imm("2039", actual)
        load(c, field, 1)
        c.emit("b081")
        c.branch(6, "stale")
    c.imm("2039", nb.STATE + nb.PHASE)
    for phase, action in enumerate(
        (ARM_WAITING, ARM_RECORDING, ARM_PROCESSING, ARM_LOADING, ARM_CANCELLING), 1
    ):
        c.imm("0c80", phase)
        c.branch(7, f"action{action}")
    c.emit("4a80")
    c.branch(6, f"action{ARM_FAILED}")
    c.imm("2039", nb.STATE + nb.RESULT)
    for result, action in (
        (1, ARM_READY),
        (-2, ARM_CANCELLED),
        (-5, ARM_STALE),
        (nb.CAPACITY_RESULT, ARM_CAPACITY),
    ):
        c.imm("0c80", result)
        c.branch(7, f"action{action}")
    c.imm("2039", nb.STATE + nb.CANCEL)
    c.emit("4a80")
    c.branch(6, f"action{ARM_CANCELLED}")
    c.branch(0, f"action{ARM_FAILED}")
    c.label("stale")
    c.branch(0, f"action{ARM_STALE}")
    for action in (ARM_WAITING, *range(ARM_RECORDING, ARM_CAPACITY + 1)):
        c.label(f"action{action}")
        setv(c, ACTION, action)
        c.branch(0, "return")
    c.label("return")
    c.emit("4e75")
    return c.finish(ARM_FEEDBACK)


def clear_canvas():
    """Clear only an authenticated native 128x64 bitmap through stock memset.

    The rectangle helper left changed-glyph-only redraws in this emulator.
    Do not assume another bitmap's storage size or mutate global panel pointers.
    """
    c = Code()
    c.emit("206f0004")
    for offset, value in ((4, 128), (8, 64), (12, 2)):
        c.emit(f"2028{offset:04x}")
        c.imm("0c80", value)
        c.branch(6, "bad")
    c.emit("20280010 4a80")
    c.branch(7, "bad")
    c.emit("48780400 7200 2f01 2f00")
    call(c, 0x401360F4, 12)
    c.emit("7001 4e75")
    c.label("bad")
    c.emit("7000 4e75")
    return c.finish(CLEAR)


def draw(
    strings,
    *,
    arm_enabled=False,
    arm_diagnostics=False,
    clock_fix=False,
    operation_diagnostics=False,
):
    c = Code()
    c.emit("4fefffa0 48d77cfc 246f0064 266f0068")
    load(c, DRAWS)
    c.emit("5280")
    store(c, DRAWS)
    if arm_enabled:
        call(c, ARM_FEEDBACK)

    def text(y, pointer=None):
        c.imm("4879", LINE if pointer is None else pointer)
        for arg in (0x20, y, 2, FONT):
            c.imm("4879", arg)
        c.emit("2f0b")
        call(c, TEXT, 24)

    def fmt(label, args):
        for arg in reversed(args):
            if isinstance(arg, int):
                c.imm("4879", arg)
            else:
                c.emit(arg)
        c.imm("4879", strings[label])
        c.imm("4879", LINE)
        call(c, PRINT, (len(args) + 2) * 4)

    def table(table_at, count):
        clamp(c, 0, count - 1, "table" + str(len(c.data)))
        c.emit("d080 d080")
        c.imm("41f9", table_at)
        c.emit("d1c0 2010")

    c.emit("2f0b")
    call(c, CLEAR, 4)
    c.emit("4a80")
    c.branch(7, "done")
    load(c, PAGE)
    c.emit("4a80")
    c.branch(6, "takes")
    fmt("title", ["2f39" + f"{STATE + BUF:08x}"])
    text(56)
    # Native source/category and channel labels; getters take live wrapper.
    c.emit("2f2a014c")
    call(c, GETTERS[0], 4)
    c.emit("2400 2f00 2f0a")
    call(c, 0x4001FD88, 8)
    c.emit("2800 2f02 2f0a")
    call(c, 0x4001FDBE, 8)
    c.emit("2c00 2f2a014c")
    call(c, GETTERS[1], 4)
    c.emit("2f00 2f0a")
    call(c, 0x4001FDF4, 8)
    c.emit("2600")
    fmt("source", ["2f04", "2f06", "2f03"])
    text(48)
    c.emit("2f2a014c")
    call(c, GETTERS[2], 4)
    table(TEXTS, 9)
    c.emit("2400 2f2a014c")
    call(c, GETTERS[3], 4)
    table(TEXTS + 36, 2)
    c.emit("2600")
    fmt("length", ["2f02", "2f03"])
    text(40)
    call(c, 0x4019988A)
    c.emit("2f00")
    call(c, 0x40015F6C, 4)
    table(TEXTS + 44, 5)
    c.emit("2400")
    c.imm("2039", nb.STATE + nb.PHASE)
    table(TEXTS + 64, 6)
    c.emit("2600")
    fmt("status", ["2f02", "2f03"])
    text(32)
    for i, y in ((1, 24), (3, 16)):
        for index, reg in ((i, "2400"), (i + 1, "2600")):
            c.imm("4879", index)
            call(c, READY, 4)
            c.emit("4a80")
            c.branch(7, f"empty{index}")
            c.imm("203c", strings["ready_buf"])
            c.branch(0, f"buf{index}")
            c.label(f"empty{index}")
            c.imm("203c", strings["empty_buf"])
            c.label(f"buf{index}")
            c.emit(reg)
        fmt("pair", [i, "2f02", i + 1, "2f03"])
        text(y)
    load(c, ACTION)
    if clock_fix:
        c.emit("4a80")
        c.branch(6, "action_feedback")
        for at in (freeze_jobs.STATE + 56, freeze_jobs.STOCK_BUSY):
            c.imm("2039", at)
            c.emit("4a80")
            c.branch(6, "sample_wait")
        c.label("action_feedback")
        load(c, ACTION)
    if arm_diagnostics:
        for action in (9, 10, 11):
            c.imm("0c80", action)
            c.branch(7, "arm_diagnostic")
        c.label("normal_feedback")
    load(c, LATCH, 2)
    c.imm("0c80", ARM_WAITING)
    c.branch(7, "arm_target")
    c.imm("0c80", ARM_RECORDING)
    c.branch(5, "feedback_label")
    c.imm("0c80", ARM_CAPACITY)
    c.branch(2, "feedback_label")
    c.label("arm_target")
    load(c, ARM_BUF, 2)
    c.label("feedback_label")
    table(TEXTS + 88, 29)
    c.emit("2f02 2f00")
    c.imm("4879", LINE)
    call(c, PRINT, 12)
    if arm_diagnostics:
        c.branch(0, "feedback_printed")
        c.label("arm_diagnostic")
        load(c, ARM_DIAG)
        c.emit("4a80")
        c.branch(7, "normal_feedback")
        diagnostic_count = (
            len(nb.ARM_DIAGNOSTICS)
            + (len(nb.CLOCK_DIAGNOSTICS) if clock_fix else 0)
            + (len(OP_DIAGNOSTICS) if operation_diagnostics else 0)
        )
        c.imm("0c80", diagnostic_count)
        c.branch(2, "normal_feedback")
        c.emit("5380")  # ID 1..N becomes a table offset 0..N-1.
        table(TEXTS + 88 + 29 * 4, diagnostic_count)
        c.emit("2f39" + f"{STATE + ARM_DIAG_VALUE:08x}" + " 2f00")
        c.imm("4879", LINE)
        call(c, PRINT, 12)
        c.label("feedback_printed")
    text(9)
    if clock_fix:
        c.branch(0, "navigation")
        c.label("sample_wait")
        text(9, strings["wait_samples"])
        c.label("navigation")
    text(3, strings["nav"])
    c.branch(0, "done")
    c.label("takes")
    load(c, FIRST)
    c.emit("2400 5280 2202")
    c.imm("0681", 4)
    fmt("takes", ["2f00", "2f01"])
    text(56)
    c.emit("7800")  # Count entries visible on this page.
    for row in range(4):
        load(c, FIRST)
        c.imm("0680", row)
        c.emit("ed88")  # index * 64
        c.imm("45f9", frozen.SNAP)
        c.emit("d5c0 2012")
        c.imm("0c80", 1)
        c.branch(6, f"take_skip{row}")
        c.emit("202a0008")
        c.imm("2239", frozen.STATE)
        c.emit("b081")
        c.branch(6, f"take_skip{row}")
        c.emit("242a0024")
        c.imm("0c82", 1023)
        c.branch(2, f"take_skip{row}")
        c.emit("2002 d080 d080 d080 d080")
        c.imm("41f9", 0x405B1368)
        c.emit("d1c0")
        for offset in range(0, 16, 4):
            c.emit(f"2028{offset:04x} 222a{offset + 16:04x} b081")
            c.branch(6, f"take_skip{row}")
        c.emit("20280008 4a80")
        c.branch(7, f"take_skip{row}")
        c.emit("2028000c 4a80")
        c.branch(7, f"take_skip{row}")
        c.emit("2002 d080 d080 d080 d080")
        c.imm("0680", 0x405B6368)
        c.emit("2600 2004 5280 2800")
        fmt("take", ["2f02", "2f03"])
        text(44 - row * 9)
        c.label(f"take_skip{row}")
    c.emit("4a84")
    c.branch(6, "takes_footer")
    text(35, strings["none"])
    c.label("takes_footer")
    text(3, strings["takes_nav"])
    c.label("done")
    c.emit("4cd77cfc 4fef0060 4e75")
    return c.finish(DRAW)


def payload(
    main,
    *,
    arm_enabled=False,
    freeze_enabled=False,
    arm_diagnostics=False,
    clock_fix=False,
    operation_diagnostics=False,
):
    """All feature behavior is emitted ColdFire; installation only is Python."""
    require(
        hashlib.sha256(main).hexdigest() == STOCK_SHA,
        "Sketch requires stock OS 1.16 MAIN",
    )
    strings, data, cursor = {}, {}, STRINGS
    labels = dict(LABELS)
    if arm_diagnostics:
        require(arm_enabled, "ARM diagnostics require real ARM")
        for index, (name, result) in enumerate(nb.ARM_DIAGNOSTICS, 1):
            category = "BUSY" if result == nb.ARM_BUSY else "REF"
            labels[f"arm_diag_{index}"] = f"{category} {name} %u"
        if operation_diagnostics or clock_fix:
            labels["arm_diag_4"] = "BUSY SAMPLE %u"
        if operation_diagnostics:
            for index, name in enumerate(OP_DIAGNOSTICS, len(nb.ARM_DIAGNOSTICS) + 1):
                labels[f"arm_diag_{index}"] = f"BUSY {name} %u"
        if clock_fix:
            labels["wait_samples"] = "WAIT SAMPLES"
            for index, name in enumerate(
                nb.CLOCK_DIAGNOSTICS, len(nb.ARM_DIAGNOSTICS) + 1
            ):
                labels[f"arm_diag_{index}"] = f"CLK {name} %u"
    for name, value in labels.items():
        raw = value.encode("ascii") + b"\0"
        strings[name] = cursor
        data[cursor] = raw
        cursor += len(raw)
    require(cursor < LINE, "Sketch strings overflow")
    words = [strings[f"len{i}"] for i in range(9)]
    words += [
        strings[n]
        for n in ("off", "on", "ready", "armed", "recording", "processing", "trim")
    ]
    words += [
        strings[n]
        for n in ("idle", "armed", "recording", "processing", "commit", "failed")
    ]
    words += [
        strings[n]
        for n in (
            ("hint_both" if arm_enabled else "hint_freeze")
            if freeze_enabled
            else ("hint_live" if arm_enabled else "hint"),
            "arm",
            "freeze",
            "busy",
            "empty",
            "unsupported",
            "hint",
            "cancel",
            "arm_ok",
            "arm_busy",
            "arm_refused",
            "arm_length",
            "freeze_queued",
            "freeze_ready",
            "freeze_busy",
            "freeze_empty",
            "freeze_full",
            "freeze_refused",
            "freeze_failed",
            "freeze_stale",
            "arm_recording",
            "arm_processing",
            "arm_loading",
            "arm_cancelling",
            "arm_ready",
            "arm_cancelled",
            "arm_failed",
            "arm_stale",
            "arm_capacity",
        )
    ]
    if arm_diagnostics:
        words += [
            strings[f"arm_diag_{i}"]
            for i in range(
                1,
                len(nb.ARM_DIAGNOSTICS)
                + 1
                + (len(nb.CLOCK_DIAGNOSTICS) if clock_fix else 0)
                + (len(OP_DIAGNOSTICS) if operation_diagnostics else 0),
            )
        ]
    data[TEXTS] = struct.pack(">" + "I" * len(words), *words)
    vt = bytearray(main[0x4021DB18 - 0x40000400 : 0x4021DB64 - 0x40000400])
    for offset, target in ((0, DTOR), (8, VIEW_KEY), (16, DRAW), (0x2C, UPDATE)):
        struct.pack_into(">I", vt, 8 + offset, target)
    # Derived view adds the rotation/push slots; every other slot is View's.
    vt += struct.pack(">II", ROTATE, 0x4011ACFC)
    data[VTABLE - 8] = bytes(vt)
    data[SHARED + 0x50] = main[0x4021DB64 - 0x40000400 : 0x4021DB78 - 0x40000400]
    secondary = bytearray(data[SHARED + 0x50])
    struct.pack_into(">I", secondary, 16, VIEW_KEY + 0x100)
    data[SHARED + 0x50] = bytes(secondary)
    thunk = Code()
    thunk.emit("206f0004 41e8fffc 2f480004")
    thunk.imm("4ef9", ROTATE)
    data[VIEW_KEY + 0x100] = thunk.finish(VIEW_KEY + 0x100)
    data[SHARED] = struct.pack(">5I", 0, 0, DISPOSE, 0x4011E8FC, 0)
    # Route prefix is a complete LEA+MOVEM pair in the authenticated image.
    prefix = main[ROUTE_SITE - 0x40000400 : ROUTE_SITE - 0x40000400 + 8]
    require(prefix == bytes.fromhex("4fefffa048d77cfc"), "Sketch route prologue drift")
    r, rs = route(prefix)
    data.update(
        {
            INPUT: input_event(arm_enabled=arm_enabled, freeze_enabled=freeze_enabled),
            KEY: bridge(KEY, perf.KEY),
            MAIN_KEY: bridge(MAIN_KEY, MAIN_KEY + 0x80),
            VIEW_KEY: bridge(VIEW_KEY, 0x4011ACFC),
            OPEN: open_view(),
            DISPOSE: dispose(),
            DTOR: destructor(),
            ROTATE: rotation(),
            DRAW: draw(
                strings,
                arm_enabled=arm_enabled,
                arm_diagnostics=arm_diagnostics,
                clock_fix=clock_fix,
                operation_diagnostics=operation_diagnostics,
            ),
            ROUTE: r,
            ROUTE_STOCK: rs,
            READY: ready(),
            UPDATE: update(arm_enabled=arm_enabled),
            ARM_SUBMIT: submit_arm(
                diagnostics=arm_diagnostics,
                clock_fix=clock_fix,
                operation_diagnostics=operation_diagnostics,
            ),
            FREEZE_SUBMIT: submit_freeze(),
            FREEZE_FEEDBACK: freeze_feedback(),
            ARM_FEEDBACK: arm_feedback(),
            CLEAR: clear_canvas(),
            MAIN_KEY + 0x80: MAIN_BYTES
            + bytes.fromhex("4ef9")
            + struct.pack(">I", MAIN_SITE + 8),
        }
    )
    if operation_diagnostics:
        data[OP_DIAG] = operation_diagnosis()
    ordered = sorted(data.items())
    for (at, raw), (following, _) in zip(ordered, ordered[1:], strict=False):
        require(at + len(raw) <= following, f"Sketch overlap at {at:#x}")
    require(ordered[-1][0] + len(ordered[-1][1]) < END, "Sketch overflow")
    return data
