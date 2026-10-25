"""Bounded native selection/retry policy for the isolated BUF experiment.

The existing CPU/DSP transaction grants permission. Time only throttles retry.
Sequencer stopped is a test precondition; no shipping placement or SAVE path.
"""

import struct

from lab import recorder_freeze_code as n
from lab import recorder_freeze_worker_code as q
from lab import recorder_native_retirement as t
from lab import recorder_seat_reuse as seats
from lab import recorder_worker_code as w
from lab.emit import Code
from lab.project import ROOT, read_json, require, sha256

BASE, END = 0x10E00000, 0x10E04000
STATE = BASE
POLL, STEP, FREEZE_POLL = BASE + 0x1000, BASE + 0x1200, BASE + 0x2000
CURSOR, ATTEMPTS, LAST_TOKEN, LAST_RESULT = 0, 4, 8, 12
ACTIVE, SUCCESSES, ACTIVE_SEAT, REFUSALS = 16, 20, 24, 28
QUEUE_DENIALS, CANCELLATIONS = 32, 36
COOLDOWNS = STATE + 0x100  # Eight (token, last-attempt tick) pairs.
BACKOFF, TICK = 32768, 0x40966500
CONTROLLER, RECORDER_STATE = 0x4019988A, 0x40015F6C
STOCK_GUARDS = {
    CONTROLLER: bytes.fromhex("4e56fff02f0a"),
    RECORDER_STATE: bytes.fromhex("206f00042f68001000044ef94004d9d6"),
    0x4004D9D6: bytes.fromhex("206f0004202800a44e75"),
}


def contract():
    cfg = read_json(ROOT / "machines/buf-auto-retirement/contract.json")
    require(cfg["status"] == "ready", "BUF automatic cleanup contract not ready")
    require(sha256(ROOT / cfg["proposal"]) == cfg["proposal_sha256"], "BUF plan drift")
    require(cfg["dependencies"] == read_json(ROOT / "deps.lock.json"), "BUF pin drift")
    for key in (
        "approval",
        "working_artifact",
        "evidence_level",
        "controls",
        "state_matrix",
        "source_equivalence",
        "experiment",
        "validation",
        "results",
        "gaps",
        "decisions",
    ):
        require(bool(cfg[key]), "Incomplete BUF cleanup contract: " + key)
    require(cfg["experiment"]["recordings"] == 4, "BUF bounded scenario drift")
    require(
        cfg["constants"]
        == dict(BASE=BASE, END=END, BACKOFF=BACKOFF, TICK=TICK, SEATS=8),
        "BUF constants drift",
    )
    return cfg


def load(c, offset, reg=0):
    c.imm(f"{0x2039 | (reg << 9):04x}", STATE + offset)


def store(c, offset, reg=0):
    c.imm(f"{0x23C0 | reg:04x}", STATE + offset)


def increment(c, offset):
    load(c, offset)
    c.emit("5280")
    store(c, offset)


def pending(c, base, target):
    c.imm("2039", base)
    c.imm("2239", base + 4)
    c.emit("b081")
    c.branch(6, target)


def poll():
    c = Code()
    c.emit("4feffff0 48d70303")
    n.call(c, STEP)
    c.emit("4cd70303 4fef0010")
    c.imm("4ef9", t.POLL)
    return c.finish(POLL)


def step():
    c = Code()
    c.emit("4fefffd0 48d77cfc")
    c.imm("2039", w.STATE + 80)
    c.emit("4a80")
    c.branch(7, "return")  # Recorder singleton is already initialized after USE.
    n.call(c, CONTROLLER)
    c.emit("4a80")
    c.branch(7, "unknown_recorder")
    c.emit("2f00")
    n.call(c, RECORDER_STATE, 4)
    c.branch(0, "recorder")
    c.label("unknown_recorder")
    c.emit("70ff")
    c.label("recorder")
    c.emit("2a00")  # D5 = original live recorder state.
    load(c, ACTIVE, 2)
    c.emit("4a82")
    c.branch(7, "admit")
    c.imm("2639", t.STATE + t.PHASE)
    c.imm("0c83", 4)
    c.branch(7, "success")
    c.imm("0c83", 5)
    c.branch(6, "waiting")
    increment(c, REFUSALS)
    c.branch(0, "completed")
    c.label("success")
    increment(c, SUCCESSES)
    c.label("completed")
    store(c, LAST_TOKEN, 2)
    c.imm("2039", t.STATE + 12)
    store(c, LAST_RESULT)
    load(c, ACTIVE_SEAT)
    c.imm("0c80", 8)
    c.branch(4, "return")
    c.emit("d080 d080 d080")
    c.imm("47f9", COOLDOWNS)
    c.emit("d7c0 2013 b082")
    c.branch(6, "clear_active")
    c.imm("2039", TICK)
    c.emit("27400004")
    c.label("clear_active")
    c.emit("7000")
    store(c, ACTIVE)
    c.branch(0, "admit")
    c.label("waiting")
    c.emit("4a85")
    c.branch(6, "cancel")
    pending(c, q.STATE, "cancel")
    pending(c, t.STATE, "cancel")
    c.branch(0, "return")
    c.label("cancel")
    c.imm("2039", t.STATE + t.CANCEL)
    c.emit("4a80")
    c.branch(6, "return")
    c.emit("7001")
    c.imm("23c0", t.STATE + t.CANCEL)
    increment(c, CANCELLATIONS)
    c.branch(0, "return")
    c.label("admit")
    c.emit("4a85")
    c.branch(6, "return")
    pending(c, q.STATE, "return")
    pending(c, t.STATE, "return")
    for at in (w.STATE + 12, n.STATE + 24, q.STOCK_BUSY, q.STATE + 56):
        c.imm("2039", at)
        c.emit("4a80")
        c.branch(6, "return")
    c.imm("2039", t.STATE + t.PHASE)
    c.emit("4a80")
    c.branch(7, "idle_phase")
    c.imm("0c80", 4)
    c.branch(7, "idle_phase")
    c.imm("0c80", 5)
    c.branch(6, "return")
    c.label("idle_phase")
    for at in (w.STATE + 64, w.STATE + 68):
        c.imm("2039", at)
        c.emit("4a80")
        c.branch(7, "return")
    c.imm("2039", 0x80004704)
    c.emit("4a80")
    c.branch(7, "return")
    c.emit("2040 7e10")
    c.label("machines")
    c.emit("7000 102800d6 4a80")
    c.branch(6, "return")
    c.emit("41e80450")
    c.imm("0687", -1)
    c.branch(6, "machines")
    c.imm("2839", TICK)
    load(c, CURSOR)
    c.imm("0280", 7)
    c.emit("2c00 7e08")
    c.label("scan")
    c.emit("2006 5280")
    c.imm("0280", 7)
    store(c, CURSOR)
    c.emit("2006 ed88")
    c.imm("45f9", n.GEN)
    c.emit("d5c0 2012")
    c.imm("0c80", 1)
    c.branch(6, "next")
    c.emit("262a0008")
    c.imm("2239", n.STATE)
    c.emit("b681")
    c.branch(6, "next")
    c.emit("242a0004")
    c.imm("0c82", seats.FIRST_ID)
    c.branch(5, "next")
    c.imm("0c82", seats.LAST_ID)
    c.branch(2, "next")
    c.emit("2006 d080 d080 d080")
    c.imm("47f9", COOLDOWNS)
    c.emit("d7c0 2013 b082")
    c.branch(6, "roots")
    c.emit("262b0004 2204 9283")
    c.imm("0c81", BACKOFF)
    c.branch(5, "next")
    c.label("roots")
    c.imm("41f9", n.STATE + 32)
    c.emit("7a04")
    c.label("current")
    c.emit("2018")
    c.imm("0c80", 1024)
    c.branch(4, "return")
    c.emit("d080 d080 d080 d080")
    c.imm("49f9", 0x405B1368)
    c.emit("d9c0 2014 b082")
    c.branch(7, "next")
    c.imm("0685", -1)
    c.branch(6, "current")
    c.imm("41f9", n.SNAP)
    c.emit("7a08")
    c.label("frozen")
    c.emit("2010 4a80")
    c.branch(7, "next_frozen")
    c.emit("20280010 b082")
    c.branch(7, "next")
    c.label("next_frozen")
    c.emit("41e80040")
    c.imm("0685", -1)
    c.branch(6, "frozen")
    c.emit("2682 27440004")  # Tag cooldown before native queue admission.
    increment(c, ATTEMPTS)
    c.imm("23c2", t.STATE + 16)
    c.emit("7001")
    n.call(c, t.QUEUE)
    c.emit("4a80")
    c.branch(6, "queue_failed")
    store(c, ACTIVE, 2)
    store(c, ACTIVE_SEAT, 6)
    c.branch(0, "return")
    c.label("queue_failed")
    store(c, LAST_RESULT)
    store(c, LAST_TOKEN, 2)
    increment(c, QUEUE_DENIALS)
    c.branch(0, "return")
    c.label("next")
    c.emit("2006 5280")
    c.imm("0280", 7)
    c.emit("2c00")
    c.imm("0687", -1)
    c.branch(6, "scan")
    c.label("return")
    c.emit("4cd77cfc 4fef0030 4e75")
    return c.finish(STEP)


def freeze_poll():
    """Leave explicit FREEZE unconsumed until the automatic lease is released."""
    c = Code()
    c.emit("4feffff0 48d70303")
    load(c, ACTIVE)
    c.emit("4a80")
    c.branch(7, "normal")
    c.imm("2039", w.STATE + 12)
    c.imm("0c80", 3)
    c.branch(6, "normal")
    c.emit("4cd70303 4fef0010")
    c.imm("4ef9", q.TRAMP)
    c.label("normal")
    c.emit("4cd70303 4fef0010")
    c.imm("4ef9", q.POLL)
    return c.finish(FREEZE_POLL)


def payload():
    contract()
    previous = t.poll()
    tail = b"\x4e\xf9" + struct.pack(">I", q.POLL)
    require(previous.endswith(tail), "Native transaction poll tail drift")
    parts = {
        POLL: poll(),
        STEP: step(),
        FREEZE_POLL: freeze_poll(),
        t.POLL: previous[:-6] + b"\x4e\xf9" + struct.pack(">I", FREEZE_POLL),
    }
    ordered = sorted((at, body) for at, body in parts.items() if BASE <= at < END)
    for (at, body), (following, _) in zip(ordered, ordered[1:], strict=False):
        require(at + len(body) <= following, "BUF cleanup code overlap")
    require(ordered[-1][0] + len(ordered[-1][1]) <= END, "BUF cleanup overflow")
    return parts
