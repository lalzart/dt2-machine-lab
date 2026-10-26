"""Native CPU side of explicit DSP-resident Sketchbook export.

Opt-in code occupies the unused upper half of the existing retirement arena.
It retains 80 file-metadata bytes per generation, never retained CPU PCM.
"""

import struct

from lab import buf_next_bar as nb
from lab import flex_native as f
from lab import recorder_freeze_code as n
from lab import recorder_freeze_worker_code as q
from lab import recorder_native_retirement as t
from lab import recorder_worker_code as w
from lab.emit import Code
from lab.project import require
from lab.sketchbook_dsp import contract

BASE = t.BASE + 0x8000
STATE, META, NODE = BASE, BASE + 0x400, BASE + 0x800
CAPTURE, DRIVER, OLD_DRIVER = BASE + 0x1000, BASE + 0x1400, BASE + 0x1700
SEND, CONSUME, READ = BASE + 0x1900, BASE + 0x2000, BASE + 0x2600
CHECK, ADMIT, SUBMIT = BASE + 0x1C00, BASE + 0x2200, BASE + 0x2A00
WORKER, RAW_SAVE, DONE = BASE + 0x2C00, BASE + 0x2E00, BASE + 0x3000
EXCLUSIVE, GUARDS = BASE + 0x3100, BASE + 0x3200
CLOSE, POLL = BASE + 0x1800, BASE + 0x1300
ENQUEUE = BASE + 0x2800
RX, PACKET, SCRATCH = BASE + 0x4000, BASE + 0x5000, BASE + 0x6000
OLD_RETIRE = BASE + 0x1200
PHASE, SERIAL, TOKEN, EPOCH, POSITION, COUNT, RECEIVED, DEST, ERROR, AGE = range(
    0, 40, 4
)
CANCEL, CONTEXT = 48, 52
JOB, RESULT, OWNER, KIT, PROJECT, POOL, SLOT, COMPLETIONS = range(56, 88, 4)
MODE, CLOSED, COMMAND, HANDLED, COMMAND_SLOT, COMMAND_RESULT = range(88, 112, 4)
KIND = 112  # 1 explicit disk export; 2 temporary stock-preview download.
COMMAND_NAME = STATE + 0x300
PATH, LABEL, DIRECTORY = STATE + 0x100, STATE + 0x200, STATE + 0x220


def load(c, offset, reg=0):
    c.imm(f"{0x2039 | reg << 9:04x}", STATE + offset)


def store(c, offset, reg=0):
    c.imm(f"{0x23C0 | reg:04x}", STATE + offset)


def value(c, offset, number):
    c.imm("203c", number)
    store(c, offset)


def call(c, address, pops=0):
    n.call(c, address, pops)


def capture():
    """Borrow original retire(node) args; capture metadata before CPU free."""
    c = Code()
    c.emit("4feffff0 48d70c0c 246f0014 2f2a0004")
    call(c, n.LOOKUP, 4)
    c.imm("0c80", n.GEN)
    c.branch(5, "return")
    c.imm("0c80", n.GEN + 8 * 64)
    c.branch(4, "return")
    c.emit("2640")
    c.imm("223c", n.GEN)
    c.emit("9081")
    c.emit("d080")
    c.imm("41f9", META)
    c.emit(
        "d1c0 2648 7000 2680 202a0004 27400004 202a0008 27400008 202a000c 2740000c 202a0010 27400078"
    )
    c.imm("2039", n.STATE)
    c.emit("27400010 7000 27400014 206a0014 2008 4a80")
    c.branch(7, "return")
    c.emit("43eb0020")
    for _ in range(16):
        c.emit("22d8")
    c.emit("206a0014 202a000c")
    c.imm("0680", -16)
    c.emit("d1c0 43eb0060 22d8 22d8 22d8 22d8 202a0004 2f00")
    call(c, n.LOOKUP, 4)
    c.emit("2040 24280024 27420018 2002 d080 d080")
    c.imm("41f9", 0x405B5368)
    c.emit("d1c0 2010")
    c.imm("0c80", 1024)
    c.branch(2, "return")
    c.imm("223c", 52)
    c.emit("4c010800")
    c.imm("2079", 0x405A0F64)
    c.emit("d1c0 20280010 27400070 20280014 27400074 7001 2680")
    c.label("return")
    c.emit("4cd70c0c 4fef0010")
    c.imm("4ef9", OLD_RETIRE)
    return c.finish(CAPTURE)


def driver():
    """Use stock 0xbc0 RX capacity; preserve the original legacy destination."""
    c = Code()
    c.emit("4feffff0 48d70c0c")
    for offset, expected in ((20, 0x802), (28, 0xABC), (32, 0x8000488C)):
        c.emit(f"202f{offset:04x}")
        c.imm("0c80", expected)
        c.branch(6, "stock")
    c.imm("203c", 0xBC0)
    c.imm("23c0", 0x42948B08)
    c.imm("4879", RX)
    c.imm("4879", 0xBC0)
    c.emit("2f2f0020 2f2f0020")
    call(c, OLD_DRIVER, 16)
    c.emit("2400")
    c.imm("4879", 0xABC)
    c.imm("4879", RX)
    c.imm("4879", 0x8000488C)
    call(c, 0x401360AC, 12)
    call(c, CONSUME)
    c.emit("2002")
    c.branch(0, "return")
    c.label("stock")
    c.emit("2f2f0020" * 4)
    call(c, OLD_DRIVER, 16)
    c.label("return")
    c.emit("4cd70c0c 4fef0010 4e75")
    return c.finish(DRIVER)


def send():
    """Serialize the current latched request and use original LP0 publication."""
    k = contract()["constants"]
    c = Code()
    c.emit("4feffff0 48d70c0c")
    load(c, CONTEXT)
    c.emit("2640")
    load(c, SERIAL)
    c.imm("0c80", -1)
    c.branch(7, "bad")
    c.emit("5280")
    store(c, SERIAL)
    value(c, PHASE, 0)
    c.imm("41f9", PACKET)
    c.emit("7000")
    c.imm("223c", 1024)
    c.label("zero")
    c.emit("20c0")
    c.imm("0681", -1)
    c.branch(6, "zero")
    c.imm("45f9", PACKET)
    for index, number in ((0, k["TAG"]), (14, 0), (15, k["MARKER"])):
        c.imm("203c", number)
        c.emit(f"2540{index * 4:04x}")
    load(c, MODE)
    c.imm("0c80", 2)
    c.branch(7, "mode")
    c.emit("7001")
    c.label("mode")
    c.emit("25400004")
    for index, field in (
        (2, EPOCH),
        (3, TOKEN),
        (4, SERIAL),
        (11, POSITION),
        (12, COUNT),
    ):
        load(c, field)
        c.emit(f"2540{index * 4:04x}")
    for index, off in ((5, 24), (6, 112), (7, 116), (9, 40)):
        c.emit(f"202b{off:04x} 2540{index * 4:04x}")
    c.emit("7000 102b0021 25400028 222b0024 4a80")
    c.branch(7, "mono")
    c.emit("2001 e488 d080 2200")
    c.label("mono")
    c.emit("25410020")
    load(c, SERIAL, 1)
    c.emit("70ff 9081 25400034")
    for field in (RECEIVED, ERROR, AGE):
        value(c, field, 0)
    load(c, MODE)
    c.imm("0c80", 2)
    c.branch(7, "closing")
    value(c, PHASE, 1)
    value(c, CLOSED, 0)
    c.branch(0, "publish")
    c.label("closing")
    value(c, PHASE, 4)
    c.label("publish")
    c.emit("7001 2f00 2f0a")
    c.imm("4879", k["TAG"])
    call(c, 0x400CD638, 12)
    c.emit("7000")
    c.branch(0, "return")
    c.label("bad")
    c.emit("70ff")
    c.label("return")
    c.emit("4cd70c0c 4fef0010 4e75")
    return c.finish(SEND)


def consume():
    """Native interrupt-path parser. Never copies unvalidated packet bytes."""
    k = contract()["constants"]
    c = Code()
    c.emit("4fefffd8 48d73cfc")
    load(c, PHASE, 6)
    c.emit("2006")
    c.imm("0c80", 1)
    c.branch(7, "pending")
    c.imm("0c80", 4)
    c.branch(6, "return")
    c.label("pending")
    load(c, AGE)
    c.emit("5280")
    store(c, AGE)
    c.imm("0c80", 512)
    c.branch(4, "bad")
    c.imm("0c86", 4)
    c.branch(7, "envelope")
    load(c, CANCEL)
    c.emit("4a80")
    c.branch(6, "bad")
    c.label("envelope")
    c.imm("47f9", RX + k["TAIL"])
    c.emit("2013")
    c.imm("0c80", k["MAGIC"])
    c.branch(6, "return")
    for packet, field in ((4, SERIAL), (8, EPOCH), (12, TOKEN), (16, POSITION)):
        c.emit(f"202b{packet:04x}")
        load(c, field, 1)
        c.emit("b081")
        c.branch(6, "return")
    c.emit("282b0018")
    c.imm("0c84", k["PAYLOAD"])
    c.branch(2, "bad")
    c.imm("203c", 2166136261)
    c.imm("243c", 16777619)
    c.emit("204b 761f")  # 32 header bytes, countdown is count-1.
    c.label("header")
    c.emit("7200 1218 b380 4c020800")
    c.imm("0683", -1)
    c.branch(10, "header")
    c.emit("41eb0024 2604 4a83")
    c.branch(7, "checksum")
    c.label("hash")
    c.emit("7200 1218 b380 4c020800")
    c.imm("0683", -1)
    c.branch(6, "hash")
    c.label("checksum")
    c.emit("222b0020 b081")
    c.branch(6, "bad")
    c.imm("0c86", 4)
    c.branch(6, "data")
    c.emit("4a84")
    c.branch(6, "bad")
    c.emit("202b0014 4a80")
    c.branch(6, "bad")
    c.emit("202b001c")
    c.imm("0c80", 2)
    c.branch(6, "bad")
    value(c, PHASE, 5)
    c.branch(0, "return")
    c.label("data")
    c.emit("202b001c 4a80")
    c.branch(6, "bad")
    c.emit("4a84")
    c.branch(7, "bad")
    c.emit("2a2b0014")
    load(c, RECEIVED, 1)
    c.emit("ba81")
    c.branch(5, "return")
    c.branch(6, "bad")
    c.emit("2005 d084")
    load(c, COUNT, 1)
    c.emit("b081")
    c.branch(2, "bad")
    load(c, DEST)
    c.emit("2840 2005 d9c0 41eb0024 2604")
    c.label("copy")
    c.emit("18d8")
    c.imm("0683", -1)
    c.branch(6, "copy")
    c.emit("2005 d084")
    store(c, RECEIVED)
    load(c, COUNT, 1)
    c.emit("b081")
    c.branch(6, "return")
    value(c, PHASE, 2)
    c.branch(0, "return")
    c.label("bad")
    value(c, ERROR, -1)
    value(c, PHASE, 3)
    c.label("return")
    c.emit("4cd73cfc 4fef0028 4e75")
    return c.finish(CONSUME)


def check():
    """Validate the immutable save lease on the worker, before every read."""
    c = Code()
    c.emit("4feffff0 48d70c0c")
    for at, expected in ((w.STATE + 12, 4), (STATE + JOB, 2)):
        c.imm("2039", at)
        c.imm("0c80", expected)
        c.branch(6, "bad")
    load(c, CANCEL)
    c.emit("4a80")
    c.branch(6, "bad")
    for at, field in (
        (q.CURRENT_TCB, OWNER),
        (n.STATE, EPOCH),
        (0x80004704, KIT),
        (0x44F370A0, PROJECT),
        (w.STATE + 68, POOL),
    ):
        c.imm("2039", at)
        load(c, field, 1)
        c.emit("b081")
        c.branch(6, "bad")
        c.emit("4a80")
        c.branch(7, "bad")
    load(c, CONTEXT)
    c.imm("0c80", META)
    c.branch(5, "bad")
    c.imm("0c80", META + 1024)
    c.branch(4, "bad")
    c.emit("2640 2013")
    c.imm("0c80", 1)
    c.branch(6, "bad")
    c.emit("202b0010")
    load(c, EPOCH, 1)
    c.emit("b081")
    c.branch(6, "bad")
    c.emit("202b0004")
    load(c, TOKEN, 1)
    c.emit("b081")
    c.branch(6, "bad")
    c.emit("2f00")
    call(c, n.LOOKUP, 4)
    c.emit("4a80")
    c.branch(7, "bad")
    c.emit("2440 2012")
    c.imm("0c80", 1)
    c.branch(6, "bad")
    for meta, gen in ((4, 16), (8, 20), (12, 24), (120, 28), (24, 36)):
        c.emit(f"202b{meta:04x} 222a{gen:04x} b081")
        c.branch(6, "bad")
    c.emit("7000")
    c.branch(0, "return")
    c.label("bad")
    c.emit("70ff")
    c.label("return")
    c.emit("4cd70c0c 4fef0010 4e75")
    return c.finish(CHECK)


def admit():
    """admit(public_slot, relative_name): validate then atomically pin/export."""
    c = Code()
    c.emit("4fefff80 48d77cfc 242f0084 246f0088 47ef002c")
    # Prepare the complete path locally; a refused second call cannot modify
    # the path or context owned by an already queued save.
    c.emit("7000 1012")
    c.imm("0c80", 33)
    c.branch(5, "bad_unmasked")
    c.imm("0c80", 46)
    c.branch(7, "bad_unmasked")
    for v in (0x2F536B65, 0x74636862, 0x6F6F6B2F):
        c.imm("203c", v)
        c.emit("26c0")
    c.emit("7600")
    c.label("char")
    c.emit("7000 101a")
    c.emit("4a80")
    c.branch(7, "terminated")
    c.imm("0c83", 60)
    c.branch(4, "bad_unmasked")
    c.imm("0c80", 32)
    c.branch(5, "bad_unmasked")
    c.imm("0c80", 126)
    c.branch(2, "bad_unmasked")
    for v in (47, 92):
        c.imm("0c80", v)
        c.branch(7, "bad_unmasked")
    c.emit("16c0")
    c.imm("0683", 1)
    c.branch(0, "char")
    c.label("terminated")
    c.emit("16c0")
    c.imm("0683", 13)
    call(c, 0x4019988A)
    c.emit("4a80")
    c.branch(7, "bad_unmasked")
    c.emit("2f00")
    call(c, 0x40015F6C, 4)
    c.emit("4a80")
    c.branch(6, "bad_unmasked")
    c.emit("40c7 2007")
    c.imm("0080", 0x700)
    c.emit("46c0")
    for at in (
        w.STATE + 12,
        n.STATE + 24,
        q.STOCK_BUSY,
        q.STATE + 56,
        nb.STATE + nb.PHASE,
    ):
        c.imm("2039", at)
        c.emit("4a80")
        c.branch(6, "bad")
    c.imm("2039", q.STATE)
    c.imm("2239", q.STATE + 4)
    c.emit("b081")
    c.branch(6, "bad")
    for at in (0x80004704, 0x44F370A0, w.STATE + 68):
        c.imm("2039", at)
        c.emit("4a80")
        c.branch(7, "bad")
    c.imm("0c82", 1)
    c.branch(5, "bad")
    c.imm("0c82", 1023)
    c.branch(2, "bad")
    c.emit("2002 d080 d080 d080 d080")
    c.imm("47f9", 0x405B1368)
    c.emit("d7c0 2f13")
    call(c, n.LOOKUP, 4)
    c.imm("0c80", n.GEN)
    c.branch(5, "bad")
    c.imm("0c80", n.GEN + 512)
    c.branch(4, "bad")
    c.emit("2440 2012")
    c.imm("0c80", 1)
    c.branch(6, "bad")
    for off in range(0, 16, 4):
        c.emit(f"202b{off:04x} 222a{16 + off:04x} b081")
        c.branch(6, "bad")
    c.emit("200a")
    c.imm("223c", n.GEN)
    c.emit("9081 d080")
    c.imm("49f9", META)
    c.emit("d9c0 2014")
    c.imm("0c80", 1)
    c.branch(6, "bad")
    for meta, gen in ((4, 16), (8, 20), (12, 24), (120, 28), (24, 36), (16, 8)):
        c.emit(f"202c{meta:04x} 222a{gen:04x} b081")
        c.branch(6, "bad")
    c.emit("202c000c")
    c.imm("0c80", 80)
    c.branch(3, "bad")
    c.emit("202c0018")
    c.imm("0c80", 1)
    c.branch(5, "bad")
    c.imm("0c80", 1023)
    c.branch(2, "bad")
    c.emit("7004")
    c.imm("23c0", w.STATE + 12)
    c.emit("200c")
    store(c, CONTEXT)
    store(c, SLOT, 2)
    c.emit("202c0004")
    store(c, TOKEN)
    for at, field in (
        (n.STATE, EPOCH),
        (0x80004704, KIT),
        (0x44F370A0, PROJECT),
        (w.STATE + 68, POOL),
    ):
        c.imm("2039", at)
        store(c, field)
    for field in (CANCEL, OWNER, PHASE, RESULT):
        value(c, field, 0)
    value(c, CLOSED, 1)
    value(c, MODE, 1)
    value(c, JOB, 1)
    c.emit("7000")
    for off in range(0, 16, 4):
        c.imm("23c0", NODE + off)
    c.emit("41ef002c")
    c.imm("43f9", PATH)
    c.label("path")
    c.emit("12d8")
    c.imm("0683", -1)
    c.branch(6, "path")
    c.emit("7000")
    c.branch(0, "restore")
    c.label("bad")
    c.emit("70ff")
    c.label("restore")
    c.emit("46c7")
    c.branch(0, "return")
    c.label("bad_unmasked")
    c.emit("70ff")
    c.label("return")
    c.emit("4cd77cfc 4fef0080 4e75")
    return c.finish(ADMIT)


def read():
    """Stock writer callback: reconstruct native file bytes into bounded scratch."""
    c = Code()
    c.emit("4fefffd8 48d73cfc 246f002c 266f0030 242f0034 262f0038")
    c.imm("0c82", 4096)
    c.branch(2, "bad")
    load(c, CONTEXT)
    c.emit("200a")
    load(c, CONTEXT, 1)
    c.emit("b081")
    c.branch(6, "bad")
    call(c, CHECK)
    c.emit("4a80")
    c.branch(6, "bad")
    c.emit("282a000c 2003 b084")
    c.branch(2, "bad")
    c.emit("2004 2203 9081 b082")
    c.branch(5, "bad")
    c.emit("2802")
    c.label("more")
    c.emit("4a84")
    c.branch(7, "ok")
    c.imm("0c83", 64)
    c.branch(5, "header")
    c.emit("2a2a000c")
    c.imm("0685", -16)
    c.emit("2003 b085")
    c.branch(4, "footer")
    # Remaining PCM bytes to the trailer; at most one request per writer chunk.
    c.emit("2005 2203 9081 2a00 b084")
    c.branch(3, "bounded")
    c.emit("2a04")
    c.label("bounded")
    store(c, COUNT, 5)
    c.emit("2003")
    c.imm("0680", -64)
    store(c, POSITION)
    c.emit("200b")
    store(c, DEST)
    call(c, SEND)
    c.emit("4a80")
    c.branch(6, "bad")
    c.imm("2c3c", 0x4000000)
    c.label("wait")
    load(c, PHASE)
    c.imm("0c80", 1)
    c.branch(6, "ready")
    c.imm("0686", -1)
    c.branch(6, "wait")
    c.branch(0, "bad")
    c.label("ready")
    c.imm("0c80", 2)
    c.branch(6, "bad")
    call(c, CHECK)
    c.emit("4a80")
    c.branch(6, "bad")
    c.emit("2005 d7c0 2003 d085 2600 2004 2205 9081 2800")
    c.branch(0, "more")
    c.label("header")
    c.emit("204a 41e80020 2003 d1c0 16d0")
    c.branch(0, "byte")
    c.label("footer")
    c.emit("2003 2205 9081 41ea0060 d1c0 16d0")
    c.label("byte")
    c.imm("0683", 1)
    c.imm("0684", -1)
    c.branch(0, "more")
    c.label("ok")
    c.emit("2002")
    c.branch(0, "return")
    c.label("bad")
    value(c, PHASE, 3)
    value(c, ERROR, -1)
    c.emit("70ff")
    c.label("return")
    c.emit("4cd73cfc 4fef0028 4e75")
    return c.finish(READ)


def submit():
    c = Code()
    c.emit("2f2f0008 2f2f0008")
    call(c, ADMIT, 8)
    c.emit("4a80")
    c.branch(6, "return")
    value(c, KIND, 1)
    c.imm("4ef9", ENQUEUE)
    c.label("return")
    c.emit("4e75")
    return c.finish(SUBMIT)


def enqueue():
    c = Code()
    c.emit("4fefffb0 48d70c0c")
    c.imm("45f9", STATE)
    c.imm("203c", q.MANAGER)
    c.imm("223c", WORKER)
    c.emit("7400 2f4a0010 2f420014 2f400018 2f41001c")
    c.imm("223c", DONE)
    c.emit("2f4a0020 2f420024 2f400028 2f41002c")
    call(c, 0x40198A16)
    c.emit("2600 47ef0020 45ef0010 2f0b 2f0a")
    c.imm("4879", LABEL)
    c.emit("2f03")
    call(c, 0x400F0AB8, 16)
    c.emit("4a80")
    c.branch(6, "ok")
    value(c, JOB, 4)
    c.emit("7000")
    c.imm("23c0", w.STATE + 12)
    c.emit("70ff")
    c.branch(0, "return")
    c.label("ok")
    c.emit("7000")
    c.label("return")
    c.emit("4cd70c0c 4fef0050 4e75")
    return c.finish(ENQUEUE)


def worker():
    c = Code()
    c.emit("4feffff8 48d70404")
    load(c, JOB)
    c.imm("0c80", 1)
    c.branch(6, "bad")
    value(c, JOB, 2)
    c.imm("2039", q.CURRENT_TCB)
    store(c, OWNER)
    call(c, CHECK)
    c.emit("4a80")
    c.branch(6, "bad")
    c.imm("4879", DIRECTORY)
    call(c, 0x40157192, 4)
    c.imm("4879", SCRATCH)
    c.imm("4879", NODE)
    c.imm("4879", PATH)
    load(c, CONTEXT)
    c.emit("2f00")
    call(c, RAW_SAVE, 16)
    c.emit("2400")
    load(c, CLOSED)
    c.imm("0c80", 1)
    c.branch(7, "closed")
    call(c, CLOSE)
    c.emit("4a80")
    c.branch(6, "bad")
    c.label("closed")
    c.emit("2002")
    c.branch(0, "return")
    c.label("bad")
    c.emit("70ff")
    c.label("return")
    c.emit("4cd70404 508f 4e75")
    return c.finish(WORKER)


def done():
    c = Code()
    c.emit("202f0008")
    store(c, RESULT)
    c.emit("4a80")
    c.branch(6, "bad")
    value(c, JOB, 3)
    c.branch(0, "unlock")
    c.label("bad")
    value(c, JOB, 4)
    c.label("unlock")
    load(c, COMPLETIONS)
    c.emit("5280")
    store(c, COMPLETIONS)
    value(c, PHASE, 0)
    load(c, CLOSED)
    c.imm("0c80", 1)
    c.branch(6, "return")
    c.emit("7000")
    c.imm("23c0", w.STATE + 12)
    c.label("return")
    c.emit("4e75")
    return c.finish(DONE)


def close():
    """Revoke the DSP reader and require its matching wire acknowledgement."""
    c = Code()
    c.emit("4feffff8 48d70404")
    value(c, MODE, 2)
    value(c, POSITION, 0)
    value(c, COUNT, 0)
    call(c, SEND)
    c.emit("4a80")
    c.branch(6, "bad")
    c.imm("243c", 0x4000000)
    c.label("wait")
    load(c, PHASE)
    c.imm("0c80", 4)
    c.branch(6, "ready")
    c.imm("0682", -1)
    c.branch(6, "wait")
    c.label("bad")
    c.emit("70ff")
    c.branch(0, "return")
    c.label("ready")
    c.imm("0c80", 5)
    c.branch(6, "bad")
    value(c, CLOSED, 1)
    c.emit("7000")
    c.label("return")
    c.emit("4cd70404 508f 4e75")
    return c.finish(CLOSE)


def poll():
    """GUI-thread command seam: selectors only, never host job completion."""
    c = Code()
    c.emit("4feffff0 48d70303")
    load(c, COMMAND)
    load(c, HANDLED, 1)
    c.emit("b081")
    c.branch(7, "return")
    store(c, HANDLED)
    c.imm("4879", COMMAND_NAME)
    load(c, COMMAND_SLOT)
    c.emit("2f00")
    call(c, SUBMIT, 8)
    store(c, COMMAND_RESULT)
    c.label("return")
    c.emit("4cd70303 4fef0010")
    c.imm("4ef9", nb.POLL)
    return c.finish(POLL)


def mutation_guard(address, fallback, is_load):
    c = Code()
    c.imm("2039", w.STATE + 12)
    c.imm("0c80", 4)
    c.branch(6, "stock")
    c.emit("70ff4e75" if is_load else "70004e75")
    c.label("stock")
    c.imm("4ef9", fallback)
    return c.finish(address)


def payload():
    raw, after_open = f.save_recording(RAW_SAVE, backing_reader=READ)
    require(raw.count(bytes.fromhex("243c00008000")) == 1, "Raw save chunk drift")
    raw = raw.replace(bytes.fromhex("243c00008000"), bytes.fromhex("243c00001000"))
    parts = {
        CAPTURE: capture(),
        DRIVER: driver(),
        OLD_DRIVER: t.driver(),
        OLD_RETIRE: w.retire(),
        SEND: send(),
        CONSUME: consume(),
        CHECK: check(),
        ADMIT: admit(),
        READ: read(),
        SUBMIT: submit(),
        ENQUEUE: enqueue(),
        WORKER: worker(),
        DONE: done(),
        CLOSE: close(),
        POLL: poll(),
        RAW_SAVE: raw,
        EXCLUSIVE: f.exclusive_open_guard(EXCLUSIVE, after_open),
    }
    for i in range(3):
        require(GUARDS + i * 128 not in parts, "Duplicate Sketchbook entry address")
        parts[GUARDS + i * 128] = mutation_guard(
            GUARDS + i * 128, t.GUARDS + i * 256, i == 0
        )
    ordered = sorted(parts.items())
    for (at, raw), (nxt, _) in zip(ordered, ordered[1:], strict=False):
        require(at + len(raw) <= nxt, "Sketchbook CPU code overlap")
    require(
        ordered[-1][0] + len(ordered[-1][1]) <= RX,
        "Sketchbook code reaches receive data",
    )
    return parts


def packet(serial, epoch, token, position, offset, data, status=0):
    """Independent test oracle; never used as the native peer's reply."""
    header = struct.pack(
        ">8I",
        contract()["constants"]["MAGIC"],
        serial,
        epoch,
        token,
        position,
        offset,
        len(data),
        status,
    )
    h = 2166136261
    for b in header + data:
        h = ((h ^ b) * 16777619) & 0xFFFFFFFF
    return header + struct.pack(">I", h) + data
