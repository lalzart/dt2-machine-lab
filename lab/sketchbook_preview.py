"""Explicit audition snapshot, owned until the stock preview reader closes it.

Saving still uses the bounded 4096-byte buffer. Only Preview allocates a full
native file temporarily; normal BUF/FREEZE storage remains on the DSP. No disk
file or sample/track association is created by audition.
"""

from lab import sketchbook_save as b
from lab.emit import Code
from lab.project import require

BASE = b.t.BASE + 0x5000
STATE = BASE
TEMP, OPENED = 0, 4
NODE = BASE + 0x40
SUBMIT = BASE + 0x1E00
DISPATCH, WORKER, DONE = BASE + 0x2400, BASE + 0x2500, BASE + 0x2800
OLD_WORKER, OLD_DONE, CLEAN = BASE + 0x2A00, BASE + 0x2C00, BASE + 0x2D00
OPEN, SIZE, READ, CLOSE = [b.BASE + x for x in (0x3400, 0x3500, 0x3600, 0x3700)]
CANCEL_KEY, OLD_ROUTE = b.BASE + 0x3800, b.BASE + 0x3C00
NAME = BASE + 0x23C0


def load(c, off, reg=0):
    c.imm(f"{0x2039 | reg << 9:04x}", STATE + off)


def store(c, off, reg=0):
    c.imm(f"{0x23C0 | reg:04x}", STATE + off)


def submit():
    c = Code()
    load(c, TEMP)
    c.emit("4a80")
    c.branch(6, "bad")
    c.imm("4879", NAME)
    c.emit("2f2f0008")
    b.call(c, b.ADMIT, 8)
    c.emit("4a80")
    c.branch(6, "return")
    b.value(c, b.KIND, 2)
    c.imm("4ef9", b.ENQUEUE)
    c.label("bad")
    c.emit("70ff")
    c.label("return")
    c.emit("4e75")
    return c.finish(SUBMIT)


def dispatch(address, fallback, target):
    c = Code()
    b.load(c, b.KIND)
    c.imm("0c80", 2)
    c.branch(6, "stock")
    c.imm("4ef9", target)
    c.label("stock")
    c.imm("4ef9", fallback)
    return c.finish(address)


def clean():
    c = Code()
    load(c, TEMP)
    c.emit("4a80")
    c.branch(7, "done")
    c.emit("2f00")
    b.call(c, 0x4011E8FC, 4)
    c.emit("7000")
    store(c, TEMP)
    store(c, OPENED)
    c.label("done")
    c.emit("4e75")
    return c.finish(CLEAN)


def worker():
    c = Code()
    c.emit("4fefffe0 48d73c3c")
    b.load(c, b.JOB)
    c.imm("0c80", 1)
    c.branch(6, "bad")
    b.value(c, b.JOB, 2)
    c.imm("2039", b.q.CURRENT_TCB)
    b.store(c, b.OWNER)
    b.call(c, b.CHECK)
    c.emit("4a80")
    c.branch(6, "bad")
    b.load(c, b.CONTEXT)
    c.emit("2440 262a000c")
    c.imm("0c83", 1_920_080)
    c.branch(2, "bad")
    c.emit("2f03")
    b.call(c, 0x4011E8F0, 4)
    c.emit("4a80")
    c.branch(7, "bad")
    c.emit("2640")
    store(c, TEMP)
    c.imm("47f9", NODE)
    for src, dst in ((4, 4), (8, 8), (12, 12), (120, 16)):
        c.emit(f"202a{src:04x} 2740{dst:04x}")
    c.emit("7000 2680")
    store(c, OPENED)
    load(c, TEMP)
    c.emit("27400014 2640 7400 7aff")
    c.label("chunk")
    c.emit("2803")
    c.imm("0c84", 4096)
    c.branch(3, "bounded")
    c.imm("283c", 4096)
    c.label("bounded")
    c.emit("204b 2002 d1c0 2f02 2f04 2f08 2f0a")
    b.call(c, b.READ, 16)
    c.emit("b084")
    c.branch(6, "finish")
    c.emit("2002 d084 2400 2003 2204 9081 2600")
    c.branch(6, "chunk")
    c.emit("7a00")
    c.label("finish")
    b.load(c, b.CLOSED)
    c.imm("0c80", 1)
    c.branch(7, "closed")
    b.call(c, b.CLOSE)
    c.emit("4a80")
    c.branch(7, "closed")
    c.emit("7aff")
    c.label("closed")
    c.emit("4a85")
    c.branch(7, "ok")
    b.call(c, CLEAN)
    c.label("bad")
    c.emit("70ff")
    c.branch(0, "return")
    c.label("ok")
    c.emit("7000")
    c.label("return")
    c.emit("4cd73c3c 4fef0020 4e75")
    return c.finish(WORKER)


def done():
    c = Code()
    b.load(c, b.KIND)
    c.imm("0c80", 2)
    c.branch(6, "stock")
    c.emit("4feffff8 48d70404 242f0010 4a82")
    c.branch(6, "commit")
    b.load(c, b.CANCEL)
    c.emit("4a80")
    c.branch(6, "failed")
    b.load(c, b.CLOSED)
    c.imm("0c80", 1)
    c.branch(6, "failed")
    c.imm("4879", NODE + 4)
    b.call(c, 0x40198948)
    c.emit("2f00")
    b.call(c, 0x40030B10, 8)
    c.imm("0280", 255)
    c.emit("4a80")
    c.branch(7, "failed")
    c.emit("7400")
    c.branch(0, "commit")
    c.label("failed")
    b.call(c, CLEAN)
    c.emit("74ff")
    c.label("commit")
    c.emit("2f02 7000 2f00")
    b.call(c, OLD_DONE, 8)
    c.emit("4cd70404 508f 4e75")
    c.label("stock")
    c.imm("4ef9", OLD_DONE)
    return c.finish(DONE)


def cancel_key():
    """Observe native STOP/NO before modal routing; keep stock event delivery."""
    c = Code()
    c.emit("4feffff0 48d70303 206f0018 2028000c")
    c.imm("0c80", 21)
    c.branch(7, "press")
    c.imm("0c80", 12)
    c.branch(6, "return")
    c.label("press")
    c.emit("20280010")
    c.imm("0280", 9)
    c.imm("0c80", 1)
    c.branch(6, "return")
    b.load(c, b.KIND)
    c.imm("0c80", 2)
    c.branch(6, "return")
    b.load(c, b.JOB)
    c.imm("0c80", 1)
    c.branch(7, "cancel")
    c.imm("0c80", 2)
    c.branch(6, "return")
    c.label("cancel")
    b.value(c, b.CANCEL, 1)
    c.label("return")
    c.emit("4cd70303 4fef0010")
    c.imm("4ef9", OLD_ROUTE)
    return c.finish(CANCEL_KEY)


def resource(op, address, fallback):
    c = Code()
    c.emit("4feffff0 48d70c0c")
    load(c, TEMP)
    c.emit("4a80")
    c.branch(7, "stock")
    if op == "size":
        c.emit("202f0014")
    elif op == "read":
        c.emit("266f001c")
        c.imm("b7fc", 0)
        c.branch(7, "stock")
        c.emit("2013")
    else:
        c.emit("246f0014")
        c.imm("b5fc", 0)
        c.branch(7, "stock")
        c.emit("2012")
    c.imm("2239", NODE + 4)
    c.emit("b081")
    c.branch(6, "stock")
    if op == "open":
        # Only the original preview loader may open this temporary source.
        c.emit("202f0010")
        c.imm("0c80", 0x40153E8A)
        c.branch(6, "bad")
        load(c, OPENED)
        c.emit("4a80")
        c.branch(6, "bad")
        for off in range(0, 16, 4):
            c.emit(f"202a{off:04x}")
            c.imm("2239", NODE + 4 + off)
            c.emit("b081")
            c.branch(6, "bad")
        c.emit("226f0018 2012 2280 7000 23400004 23400008 7001")
        store(c, OPENED)
        c.emit("7000")
    elif op == "size":
        c.imm("2039", NODE + 12)
    elif op == "close":
        load(c, OPENED)
        c.imm("0c80", 1)
        c.branch(6, "bad")
        b.call(c, CLEAN)
        c.emit("70ff 2480 7000")
    else:
        c.emit("202f0010")
        c.imm("0c80", 0x40153ED4)
        c.branch(7, "reader")
        c.imm("0c80", 0x40153D7E)
        c.branch(6, "bad")
        c.label("reader")
        load(c, OPENED)
        c.imm("0c80", 1)
        c.branch(6, "bad")
        c.emit("242f0018 222b0004")
        c.imm("2039", NODE + 12)
        c.emit("b280")
        c.branch(2, "bad")
        c.emit("9081 b480")
        c.branch(3, "bounded")
        c.emit("2400")
        c.label("bounded")
        c.emit("4a82")
        c.branch(7, "zero")
        load(c, TEMP)
        c.emit("2040 2001 d1c0 246f0014 2002")
        c.label("copy")
        c.emit("14d8")
        c.imm("0680", -1)
        c.branch(6, "copy")
        c.emit("2001 d082 27400004 2002")
        c.branch(0, "return")
        c.label("zero")
        c.emit("7000")
    c.branch(0, "return")
    c.label("bad")
    c.emit("70ff")
    c.branch(0, "return")
    c.label("stock")
    c.emit("4cd70c0c 4fef0010")
    c.imm("4ef9", fallback)
    c.label("return")
    c.emit("4cd70c0c 4fef0010 4e75")
    return c.finish(address)


def payload():
    parts = {
        SUBMIT: submit(),
        DISPATCH: dispatch(DISPATCH, OLD_WORKER, WORKER),
        WORKER: worker(),
        DONE: done(),
        OLD_WORKER: b.worker(),
        OLD_DONE: b.done(),
        CLEAN: clean(),
        CANCEL_KEY: cancel_key(),
    }
    for op, at in [("open", OPEN), ("size", SIZE), ("read", READ), ("close", CLOSE)]:
        i = list(b.n.RESOURCE_SITES).index(op)
        parts[at] = resource(op, at, b.w.DISPATCH + i * 256)
    seq = sorted(parts.items())
    for (at, raw), (nxt, _) in zip(seq, seq[1:], strict=False):
        require(at + len(raw) <= nxt, "Preview code overlap")
    require(OLD_WORKER + len(parts[OLD_WORKER]) <= OLD_DONE, "Preview worker bounds")
    require(CLEAN + len(parts[CLEAN]) <= BASE + 0x3000, "Preview code reaches backend")
    return parts
