"""Eight reusable native seats with unique tokens; paused emulator only.

No native general retirement permission, SAVE, target placement or device build.
All existing emitters remain unchanged; this adapter installs guarded overlays.
"""

import struct

from lab import recorder_dsp_reuse as r
from lab import recorder_freeze_code as n
from lab import recorder_worker_code as w
from lab.coldfire import audit_code
from lab.emit import Code
from lab.project import ROOT, read_json, require, sha256

FIRST_ID, LAST_ID = 0x7FFB0001, 0x7FFBFFFF
BASE, END = 0x10C00000, 0x10C04000
STATE = BASE  # current physical seat, never the token serial
SELECT, RESERVE, CLEAN = BASE + 0x1000, BASE + 0x1200, BASE + 0x1400
ACCEPT = BASE + 0x1A00


def contract():
    cfg = read_json(ROOT / "machines/recorder-seat-reuse/contract.json")
    require(cfg["status"] == "ready", "Seat contract not ready")
    require(sha256(ROOT / cfg["proposal"]) == cfg["proposal_sha256"], "Seat plan drift")
    require(cfg["dependencies"] == read_json(ROOT / "deps.lock.json"), "Seat pin drift")
    for key in (
        "approval",
        "target",
        "working_artifact",
        "evidence_level",
        "scope",
        "controls",
        "state_matrix",
        "source_equivalence",
        "experiment",
        "validation",
        "results",
        "gaps",
        "decisions",
    ):
        require(bool(cfg[key]), "Incomplete seat contract: " + key)
    require(cfg["experiment"]["cycles"] == 100, "Seat cycle contract drift")
    return cfg


def replace_once(block, before, after):
    require(block.count(before) == 1, "Seat overlay operand drift")
    require(len(before) == len(after), "Seat overlay changes branch offsets")
    return block.replace(before, after)


def lookup():
    c = Code()
    c.emit("202f0004")
    c.imm("0c80", FIRST_ID)
    c.branch(5, "snapshot")
    c.imm("0c80", LAST_ID)
    c.branch(2, "snapshot")
    c.imm("41f9", n.GEN)
    c.label("scan")
    c.emit("20280004 222f0004 b081")
    c.branch(7, "status")
    c.label("next")
    c.emit("41e80040")
    c.imm("b1fc", n.GEN + 8 * 64)
    c.branch(6, "scan")
    c.branch(0, "bad")
    c.label("snapshot")
    c.imm("0c80", n.SNAP_FIRST)
    c.branch(5, "bad")
    c.imm("0c80", n.SNAP_LAST)
    c.branch(2, "bad")
    c.imm("0680", -n.SNAP_FIRST)
    c.emit("ed88")
    c.imm("41f9", n.SNAP)
    c.emit("d1c0")
    c.label("status")
    c.emit("2010")
    c.imm("0c80", 1)
    c.branch(7, "epoch")
    c.imm("0c80", 2)
    c.branch(6, "bad")
    c.imm("2039", n.STATE + 24)
    c.imm("0c80", 1)
    c.branch(6, "bad")
    c.label("epoch")
    c.emit("20280008")
    c.imm("2239", n.STATE)
    c.emit("b081")
    c.branch(6, "bad")
    c.emit("20280004 222f0004 b081")
    c.branch(6, "bad")
    c.emit("2008 4e75")
    c.label("bad")
    c.emit("7000 4e75")
    return c.finish(n.LOOKUP)


def select():
    """Return vacant seat index; no ownership mutation on refusal."""
    c = Code()
    c.imm("41f9", n.GEN)
    c.emit("7000")
    c.label("scan")
    c.emit("2210 4a81")
    c.branch(7, "found")
    c.emit("41e80040")
    c.imm("0680", 1)
    c.imm("0c80", 8)
    c.branch(6, "scan")
    c.emit("70ff 4e75")
    c.label("found")
    c.emit("4e75")
    return c.finish(SELECT)


def reserve():
    """Quarantine a seat before exposing a candidate key to the loader."""
    c = Code()
    c.imm("2039", STATE)
    c.emit("ed88")
    c.imm("41f9", n.GEN)
    c.emit("d1c0 7003 2080")
    c.imm("2039", w.STATE + 4)
    c.imm("0680", FIRST_ID)
    c.emit("21400004")
    c.imm("2039", n.STATE)
    c.emit("21400008 4e75")
    return c.finish(RESERVE)


def register():
    c = Code()
    c.emit("4fefffd0 48d71c3c 242f0034 262f0038 282f003c 2a2f0040")
    c.imm("45f9", n.STATE)
    c.emit("2012 b085")
    c.branch(6, "bad")
    for bound, cond in ((1, 5), (4, 2)):
        c.imm("0c82", bound)
        c.branch(cond, "bad")
    c.imm("2039", STATE)
    c.imm("0c80", 8)
    c.branch(4, "bad")
    c.emit("ed88")
    c.imm("49f9", n.GEN)
    c.emit("d9c0 2014")
    c.imm("0c80", 3)
    c.branch(6, "bad")
    c.emit("202c0008 b085")
    c.branch(6, "bad")
    c.emit("2003 d080 d080 d080 d080")
    c.imm("47f9", 0x405B1368)
    c.emit("d7c0 2013 222c0004 b081")
    c.branch(6, "bad")
    c.emit("29450008 29440024 43ec0010 204b 22d8 22d8 22d8 22d8")
    c.emit("43ec0030 41ec0010 22d8 22d8 22d8 22d8")
    c.imm("223c", n.GEN_NAME)
    c.emit("29410020 7201 2881 25410010 2002")
    c.imm("0680", -1)
    c.emit("d080 d080")
    c.imm("41f9", n.STATE + 32)
    c.emit("d1c0 2083 7000")
    c.branch(0, "return")
    c.label("bad")
    c.emit("70ff")
    c.label("return")
    c.emit("4cd71c3c 4fef0030 4e75")
    return c.finish(n.REGISTER)


def clean():
    """After final stock unload, unlink/free the dead source node and seat."""
    c = Code()
    c.emit("4feffff0 48d70c0c 246f0014 242a0004")
    c.imm("45f9", w.STATE)
    c.label("scan")
    c.emit("2052")
    c.imm("b1fc", 0)
    c.branch(7, "vacate")
    c.emit("22280004 b481")  # compare D1,D2
    c.branch(7, "found")
    c.emit("2448")
    c.branch(0, "scan")
    c.label("found")
    c.emit("2210 2481 2f08")
    n.call(c, 0x4011E8FC, 4)
    c.label("vacate")
    c.emit("246f0014 7000 2480 4cd70c0c 4fef0010 4e75")
    return c.finish(CLEAN)


def worker(*, require_track=True):
    """Derive the old worker without editing its default emitted bytes."""
    block = w.worker(require_track=require_track)
    block = replace_once(
        block, bytes.fromhex("0c8000000008"), bytes.fromhex("0c800000ffff")
    )
    # Preserve the original worker's branches by replacing a same-size span
    # with JSR/NOPs. SELECT returns the private-seat index, not issued count.
    before = bytes.fromhex("202a0004d080d08041ea0070d1c0261025430048")
    after = bytes.fromhex("4eb9") + struct.pack(">I", BASE + 0x1600)
    block = replace_once(
        block, before, after + b"\x4e\x71" * ((len(before) - len(after)) // 2)
    )
    # Refuse full seats before any capture/allocation. Same-size call replaces
    # SETUP with a wrapper that calls original SETUP, checks seats and latches.
    block = replace_once(
        block,
        bytes.fromhex("4eb9") + struct.pack(">I", w.SETUP),
        bytes.fromhex("4eb9") + struct.pack(">I", BASE + 0x1800),
    )
    block = replace_once(
        block,
        bytes.fromhex("4eb9") + struct.pack(">I", w.ACCEPT),
        bytes.fromhex("4eb9") + struct.pack(">I", ACCEPT),
    )
    audit_code(block, w.WORKER)
    return block


def private_slot():
    c = Code()
    n.call(c, RESERVE)
    c.imm("2039", STATE)
    c.emit("d080 d080 41ea0070 d1c0 2610 25430048 4e75")
    return c.finish(BASE + 0x1600)


def setup():
    c = Code()
    n.call(c, w.SETUP)
    c.emit("4a80")
    c.branch(6, "return")
    n.call(c, SELECT)
    c.imm("0c80", -1)
    c.branch(7, "return")
    c.imm("23c0", STATE)
    c.emit("7000")
    c.label("return")
    c.emit("4e75")
    return c.finish(BASE + 0x1800)


def accept():
    """Release unexposed reservations on failure; exposed tokens quarantine."""
    c = Code()
    c.emit("4feffff8 48d70404")
    c.emit("2f2f001c" * 5)
    n.call(c, w.ACCEPT, 20)
    c.emit("2400")
    c.imm("0c80", -1)
    c.branch(6, "return")
    c.imm("2039", w.STATE + 4)
    c.imm("0680", FIRST_ID)
    c.emit("2200")
    c.imm("2039", STATE)
    c.emit("ed88")
    c.imm("45f9", n.GEN)
    c.emit("d5c0 202a0004 b081")
    c.branch(6, "return")
    c.emit("7000 2480")
    c.label("return")
    c.emit("2002 4cd70404 508f 4e75")
    return c.finish(ACCEPT)


def dispatch(op, address, native, legacy):
    c = Code()
    if op in ("resolve", "open", "close", "read"):
        c.emit("206f" + ("000c" if op == "read" else "0004"))
        c.imm("b1fc", 0)
        c.branch(7, "native")
        c.emit("2010")
    else:
        c.emit("202f0004")
    c.imm("0c80", FIRST_ID)
    c.branch(5, "native")
    c.imm("0c80", LAST_ID)
    c.branch(2, "native")
    c.emit("2f00")
    n.call(c, n.LOOKUP, 4)
    c.emit("4a80")
    c.branch(6, "native")
    c.imm("2039", w.STATE + 12)
    c.imm("0c80", 1)
    c.branch(6, "native")
    c.imm("4ef9", legacy)
    c.label("native")
    c.imm("4ef9", native)
    return c.finish(address)


def payload():
    parts = {
        n.LOOKUP: lookup(),
        n.REGISTER: register(),
        w.WORKER: worker(),
        SELECT: select(),
        RESERVE: reserve(),
        CLEAN: clean(),
        BASE + 0x1600: private_slot(),
        BASE + 0x1800: setup(),
        ACCEPT: accept(),
    }
    parts[w.ACCEPT] = w.payload()[w.ACCEPT]
    parts[w.ACCEPT] = replace_once(
        parts[w.ACCEPT], bytes.fromhex("0c8000000020"), bytes.fromhex("0c800000ffff")
    )
    parts[w.ACCEPT] = replace_once(
        parts[w.ACCEPT],
        bytes.fromhex("0680") + struct.pack(">I", n.FIRST_ID),
        bytes.fromhex("0680") + struct.pack(">I", FIRST_ID),
    )
    for i, (op, _) in enumerate(n.RESOURCE_SITES.items()):
        for address, block in (
            (
                n.HANDLERS + i * 512,
                n.resource(op, n.HANDLERS + i * 512, n.TRAMPOLINES + i * 32),
            ),
            (w.LEGACY + i * 512, w.payload()[w.LEGACY + i * 512]),
        ):
            for before, after in ((n.FIRST_ID, FIRST_ID), (n.LAST_ID, LAST_ID)):
                block = block.replace(
                    struct.pack(">I", before), struct.pack(">I", after)
                )
            parts[address] = block
        parts[w.DISPATCH + i * 256] = dispatch(
            op, w.DISPATCH + i * 256, n.HANDLERS + i * 512, w.LEGACY + i * 512
        )
    parts[r.ENTRY] = r.command(
        first_id=FIRST_ID, last_id=LAST_ID, lookup=n.LOOKUP, after_release=CLEAN
    )
    for address, block in parts.items():
        audit_code(block, address)
    ordered = sorted(parts.items())
    for (at, block), (next_at, _) in zip(ordered, ordered[1:], strict=False):
        require(at + len(block) <= next_at, "Seat payload overlap")
    return parts


def build_diagnostic(output, *, gate_state=None):
    """Rebuild inherited diagnostic with only its accepted ID range changed."""
    from copy import deepcopy

    from lab import recorder_retirement as observer
    from lab import recorder_retirement_gate as gate

    contract()
    original = observer.contract
    cfg = deepcopy(original())
    cfg["constants"].update(FIRST_ID=FIRST_ID, LAST_ID=LAST_ID)
    observer.contract = lambda: cfg
    try:
        return gate.build(output, state_base=gate_state)
    finally:
        observer.contract = original
