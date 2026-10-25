"""Native performance FREEZE chord around the isolated ONESHOT BUF workflow."""

import struct

from lab import arp_firmware as bridge
from lab import buf_auto_retirement as auto
from lab import recorder_freeze_code as n
from lab import recorder_freeze_worker_code as q
from lab import recorder_seat_reuse as seats
from lab import recorder_worker_code as w
from lab.emit import Code
from lab.project import ROOT, read_json, require, sha256

BASE, END = 0x10F00000, 0x10F04000
STATE = BASE
KEY, INPUT, ELIGIBLE = BASE + 0x1000, BASE + 0x1200, BASE + 0x1800
SUBMIT, RAW_SUBMIT = BASE + 0x1D00, BASE + 0x2000
DEST, EPOCH, KIT, SAMPLING_OWNED, REQUESTS, REFUSALS, C_OWNED = range(0, 28, 4)
KEY_SITE, PLAY_GET, HELD = 0x4005DC58, 0x400D6726, 0x4011DE70
KEY_BYTES = bytes.fromhex("4e56ffa448d73cfc")
PLAY_BYTES = bytes.fromhex("20394316501080b943164f944e75")


def contract():
    c = read_json(ROOT / "machines/buf-performance/contract.json")
    require(c["status"] == "ready", "BUF performance contract not ready")
    require(sha256(ROOT / c["proposal"]) == c["proposal_sha256"], "BUF plan drift")
    require(c["dependencies"] == read_json(ROOT / "deps.lock.json"), "BUF pins drift")
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
        require(bool(c[key]), "Incomplete performance contract: " + key)
    require(c["experiment"]["recordings"] == 4, "BUF performance scenario drift")
    require(
        c["constants"]
        == dict(
            BASE=BASE,
            END=END,
            PLAY_GET=PLAY_GET,
            SAMPLING=50,
            FREEZE_KEY=43,
            KEY_SITE=KEY_SITE,
        ),
        "BUF performance constants drift",
    )
    return c


def load(c, field, reg=0):
    c.imm(f"{0x2039 | (reg << 9):04x}", STATE + field)


def store(c, field, reg=0):
    c.imm(f"{0x23C0 | reg:04x}", STATE + field)


def eligible(*, all_oneshot=True):
    c = Code()
    c.emit("4fefffd0 48d77cfc")
    for at in (w.STATE + 64, w.STATE + 68, w.STATE + 80):
        c.imm("2039", at)
        c.emit("4a80")
        c.branch(7, "bad")
    n.call(c, PLAY_GET)
    c.imm("0c80", 1)
    c.branch(6, "bad")
    n.call(c, auto.CONTROLLER)
    c.emit("4a80")
    c.branch(7, "bad")
    c.emit("2f00")
    n.call(c, auto.RECORDER_STATE, 4)
    c.emit("4a80")
    c.branch(6, "bad")
    for at in (n.STATE + 24, q.STOCK_BUSY, q.STATE + 56):
        c.imm("2039", at)
        c.emit("4a80")
        c.branch(6, "bad")
    c.imm("2039", q.STATE)
    c.imm("2239", q.STATE + 4)
    c.emit("b081")
    c.branch(6, "bad")
    c.imm("0c80", -1)
    c.branch(7, "bad")
    c.imm("2039", w.STATE + 12)
    c.emit("4a80")
    c.branch(7, "idle")
    c.imm("0c80", 3)  # Existing automatic lease yields to explicit FREEZE.
    c.branch(6, "bad")
    c.imm("2039", auto.STATE + auto.ACTIVE)
    c.emit("4a80")
    c.branch(7, "bad")
    c.label("idle")
    c.imm("2039", 0x80004704)
    c.emit("4a80")
    c.branch(7, "bad")
    c.emit("2440")
    if all_oneshot:
        c.emit("2040 7610")
        c.label("machines")
        c.emit("7000 102800d6 4a80")
        c.branch(6, "bad")
        c.emit("41e80450")
        c.imm("0683", -1)
        c.branch(6, "machines")
    n.call(c, 0x401988A2)
    c.emit("2f00")
    n.call(c, 0x40041D18, 4)
    c.emit("4a80")
    c.branch(7, "bad")
    c.emit("2f00")
    n.call(c, 0x4004ABE8, 4)
    c.imm("0c80", 15)
    c.branch(2, "bad")
    c.imm("223c", 0x450)
    c.emit("4c010800 204a d1c0 7600 36280080")
    c.imm("0c83", 1024)
    c.branch(4, "bad")
    c.imm("41f9", n.STATE + 32)
    c.emit("7401")
    c.label("buffers")
    c.emit("2018 4a80")
    c.branch(7, "next")
    c.emit("b083")
    c.branch(7, "found")
    c.label("next")
    c.imm("0682", 1)
    c.imm("0c82", 5)
    c.branch(6, "buffers")
    c.branch(0, "bad")
    c.label("found")
    c.emit("2003 d080 d080 d080 d080")
    c.imm("43f9", 0x405B1368)
    c.emit("d3c0 2011")
    c.imm("0c80", seats.FIRST_ID)
    c.branch(5, "bad")
    c.imm("0c80", seats.LAST_ID)
    c.branch(2, "bad")
    c.emit("2002")
    c.branch(0, "return")
    c.label("bad")
    c.emit("70ff")
    c.label("return")
    c.emit("4cd77cfc 4fef0030 4e75")
    return c.finish(ELIGIBLE)


def input_event():
    c = Code()
    c.emit(bridge.PRESAVE + " 266f002c 242b000c 262b0010")
    c.imm("0c82", 50)
    c.branch(6, "c_key")
    load(c, SAMPLING_OWNED)
    c.emit("4a80")
    c.branch(7, "stock")
    c.emit("2003")
    c.imm("0280", 9)
    c.emit("4a80")
    c.branch(6, "consumed")
    c.emit("7000")
    store(c, SAMPLING_OWNED)
    c.branch(0, "consumed")
    c.label("c_key")
    c.imm("0c82", 43)
    c.branch(6, "stock")
    for field in (SAMPLING_OWNED, C_OWNED):
        load(c, field)
        c.emit("4a80")
        c.branch(6, "owned_c")
    c.imm("0c83", 1)  # Plain press only; repeats and modified keys stay stock.
    c.branch(6, "stock")
    c.imm("4879", 50)
    n.call(c, HELD, 4)
    c.emit("4a80")
    c.branch(7, "stock")
    for key in (17, 10, 12, 20, 21):
        c.imm("4879", key)
        n.call(c, HELD, 4)
        c.emit("4a80")
        c.branch(6, "stock")
    n.call(c, ELIGIBLE)
    c.imm("0c80", 1)
    c.branch(5, "refused")
    c.imm("0c80", 4)
    c.branch(2, "refused")
    store(c, DEST)
    for actual, field in ((n.STATE, EPOCH), (0x80004704, KIT)):
        c.imm("2039", actual)
        store(c, field)
    for field in (SAMPLING_OWNED, C_OWNED):
        c.emit("7001")
        store(c, field)
    load(c, REQUESTS)
    c.emit("5280")
    store(c, REQUESTS)
    c.imm("2039", q.STATE)
    c.emit("5280")
    c.imm("23c0", q.STATE)
    c.branch(0, "consumed")
    c.label("owned_c")
    c.emit("2003")
    c.imm("0280", 8)
    c.emit("4a80")
    c.branch(6, "consumed")
    c.emit("2003")
    c.imm("0280", 1)
    store(c, C_OWNED)
    c.branch(0, "consumed")
    c.label("refused")
    load(c, REFUSALS)
    c.emit("5280")
    store(c, REFUSALS)
    c.label("stock")
    c.emit("7000")
    c.branch(0, "return")
    c.label("consumed")
    c.emit("7001")
    c.label("return")
    c.emit(bridge.RESTORE + " 4e75")
    return c.finish(INPUT)


def submit():
    c = Code()
    for actual, field in ((n.STATE, EPOCH), (0x80004704, KIT)):
        c.imm("2039", actual)
        load(c, field, 1)
        c.emit("b081")
        c.branch(6, "stale")
    c.imm("4ef9", RAW_SUBMIT)
    c.label("stale")
    c.emit("70f8")
    c.imm("23c0", q.STATE + 52)
    c.emit("4e75")
    return c.finish(SUBMIT)


def payload():
    contract()
    raw = q.submit()
    old, new = struct.pack(">I", w.DEST), struct.pack(">I", STATE + DEST)
    require(raw.count(old) == 1, "FREEZE selected-buffer operand drift")
    parts = {
        KEY: bridge.key_hook(KEY, {"input": INPUT}, KEY_SITE, True),
        INPUT: input_event(),
        ELIGIBLE: eligible(),
        SUBMIT: submit(),
        RAW_SUBMIT: raw.replace(old, new),
    }
    ordered = sorted(parts.items())
    for (at, data), (after, _) in zip(ordered, ordered[1:], strict=False):
        require(at + len(data) <= after, "Performance code overlap")
    require(ordered[-1][0] + len(ordered[-1][1]) <= END, "Performance overflow")
    return parts
