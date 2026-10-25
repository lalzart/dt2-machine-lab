"""Native worker/ISR retirement for the guarded volatile private namespace.

No paused certificate, host diagnostic delivery, firmware placement or device
claim. Capture, LP0 delivery and the prepared SEC reset contents remain modeled.
"""

import hashlib
import re
import struct

from lab import recorder_ack as ack
from lab import recorder_ack_loop as loop
from lab import recorder_freeze_code as n
from lab import recorder_freeze_worker_code as q
from lab import recorder_retirement as observer
from lab import recorder_seat_reuse as seats
from lab import recorder_worker_code as w
from lab.emit import Code
from lab.project import ROOT, read_json, require, sha256, write_json

MACHINE = ROOT / "machines/recorder-native-retirement"
BASE, END = 0x10D00000, 0x10D10000
STATE = BASE
POLL, QUEUE, MANAGER = BASE + 0x1000, BASE + 0x1400, BASE + 0x1800
WORKER, DONE, BEGIN = BASE + 0x1A00, BASE + 0x1D00, BASE + 0x2000
VALIDATE, COMMIT, DRIVER = BASE + 0x2400, BASE + 0x3000, BASE + 0x3400
RAW_DRIVER, LOOKUP_GUARD, RAW_LOOKUP = BASE + 0x3800, BASE + 0x3900, BASE + 0x3A00
GUARDS, LABEL = BASE + 0x4000, BASE + 0x500
DRIVER_SITE = 0x400CD2BC
DRIVER_BYTES = bytes.fromhex("2f0a2f02222f0014")
# Input serial/handled/phase/result, input token/token/epoch/kit/owner/sequence,
# entry/private/start/size, reserved/cancel, polls/completions/mode,
# reserved/inflight/successes/resource-denials/wire-denials/queue-denials.
PHASE, TOKEN, EPOCH, KIT, OWNER, SEQ = 8, 20, 24, 28, 32, 36
ENTRY, PRIVATE, START, SIZE, CANCEL, SUCCESSES = 40, 44, 48, 52, 60, 84
ACTIVE_UNLOAD = 80


def contract():
    c = read_json(MACHINE / "contract.json")
    require(c["status"] == "ready", "Native retirement contract not ready")
    require(
        sha256(ROOT / c["proposal"]) == c["proposal_sha256"], "Retirement plan drift"
    )
    require(
        c["dependencies"] == read_json(ROOT / "deps.lock.json"), "Retirement pin drift"
    )
    for name in (
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
        require(bool(c[name]), "Incomplete retirement contract: " + name)
    require(c["constants"]["FRAGMENTS"] == 64, "Retirement domain missing")
    require(c["experiment"]["cycles"] == 100, "Retirement cycle contract drift")
    return c


def load(c, offset, reg=0):
    c.emit(f"{0x2039 | (reg << 9):04x}")
    c.data.extend(struct.pack(">I", STATE + offset))


def store(c, offset, reg=0):
    c.imm(f"{0x23C0 | reg:04x}", STATE + offset)


def value(c, offset, number):
    c.imm("203c", number)
    store(c, offset)


def call(c, address, pops=0):
    n.call(c, address, pops)


def poll():
    c = Code()
    c.emit("4feffff0 48d70303")
    load(c, PHASE)
    c.imm("0c80", 2)
    c.branch(6, "input")
    load(c, CANCEL)
    c.emit("4a80")
    c.branch(6, "expired")
    c.imm("2039", ack.constants()["CF_STATE"] + ack.PHASE)
    c.imm("0c80", 3)
    c.branch(7, "expired")
    c.imm("0c80", 2)
    c.branch(6, "input")
    c.emit("7002")
    call(c, QUEUE)
    c.branch(0, "input")
    c.label("expired")
    value(c, PHASE, 5)
    value(c, 12, -6)
    c.emit("7000")
    c.imm("23c0", w.STATE + 12)
    c.imm("23c0", ack.constants()["CF_STATE"] + ack.PHASE)
    c.label("input")
    load(c, 0)
    load(c, 4, 1)
    c.emit("b081")
    c.branch(7, "return")
    store(c, 4)
    c.emit("7001")
    call(c, QUEUE)
    c.label("return")
    c.emit("4cd70303 4fef0010")
    c.imm("4ef9", q.POLL)
    return c.finish(POLL)


def queue():
    c = Code()
    c.emit("4fefffb0 48d70c0c 2400")
    c.imm("0c82", 1)
    c.branch(6, "commit")
    for at in (w.STATE + 12, n.STATE + 24, q.STOCK_BUSY, q.STATE + 56):
        c.imm("2039", at)
        c.emit("4a80")
        c.branch(6, "deny")
    load(c, 16)
    store(c, TOKEN)
    c.imm("2039", n.STATE)
    store(c, EPOCH)
    c.imm("2039", 0x80004704)
    store(c, KIT)
    value(c, CANCEL, 0)
    value(c, 100, 0)
    value(c, OWNER, 0)
    value(c, PHASE, 1)
    c.emit("7003")
    c.imm("23c0", w.STATE + 12)
    c.branch(0, "enqueue")
    c.label("commit")
    c.imm("2039", w.STATE + 12)
    c.imm("0c80", 3)
    c.branch(6, "deny")
    load(c, PHASE)
    c.imm("0c80", 2)
    c.branch(6, "deny")
    value(c, PHASE, 3)
    c.label("enqueue")
    store(c, 72, 2)
    c.imm("45f9", STATE)
    c.imm("203c", MANAGER)
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
    value(c, PHASE, 5)
    value(c, 12, -7)
    c.emit("7000")
    c.imm("23c0", w.STATE + 12)
    c.label("deny")
    load(c, 96)
    c.emit("5280")
    store(c, 96)
    c.emit("70ff")
    c.branch(0, "return")
    c.label("ok")
    c.emit("7000")
    c.label("return")
    c.emit("4cd70c0c 4fef0050 4e75")
    return c.finish(QUEUE)


def worker():
    c = Code()
    c.emit("4feffff8 48d70404")
    load(c, 72)
    c.imm("0c80", 1)
    c.branch(6, "commit")
    c.imm("2039", q.CURRENT_TCB)
    store(c, OWNER)
    call(c, BEGIN)
    c.branch(0, "return")
    c.label("commit")
    call(c, COMMIT)
    c.label("return")
    c.emit("4cd70404 508f 4e75")
    return c.finish(WORKER)


def done():
    c = Code()
    c.emit("202f0008")
    store(c, 12)
    c.emit("4a80")
    c.branch(6, "failed")
    load(c, 72)
    c.imm("0c80", 1)
    c.branch(6, "complete")
    value(c, PHASE, 2)
    c.emit("4e75")
    c.label("complete")
    value(c, PHASE, 4)
    c.branch(0, "unlock")
    c.label("failed")
    value(c, PHASE, 5)
    c.label("unlock")
    load(c, 68)
    c.emit("5280")
    store(c, 68)
    c.emit("7000")
    c.imm("23c0", w.STATE + 12)
    c.imm("23c0", ack.constants()["CF_STATE"] + ack.PHASE)
    c.emit("4e75")
    return c.finish(DONE)


def validate():
    c = Code()
    c.emit("4fefffd0 48d77cfc")
    c.imm("2039", w.STATE + 12)
    c.imm("0c80", 3)
    c.branch(6, "bad")
    load(c, PHASE)
    c.imm("0c80", 1)
    c.branch(7, "phase_ok")
    c.imm("0c80", 3)
    c.branch(6, "bad")
    c.label("phase_ok")
    for at in (n.STATE + 24, q.STATE + 56, q.STOCK_BUSY):
        c.imm("2039", at)
        c.emit("4a80")
        c.branch(6, "bad")
    load(c, CANCEL)
    c.emit("4a80")
    c.branch(6, "bad")
    load(c, OWNER)
    c.imm("2239", q.CURRENT_TCB)
    c.emit("b081 4a80")
    # Test equality before the nonzero test changes flags.
    c.emit("b081")
    c.branch(6, "bad")
    c.emit("4a80")
    c.branch(7, "bad")
    for actual, field in ((n.STATE, EPOCH), (0x80004704, KIT)):
        c.imm("2039", actual)
        load(c, field, 1)
        c.emit("b081")
        c.branch(6, "stale")
    load(c, TOKEN, 2)
    c.imm("0c82", seats.FIRST_ID)
    c.branch(5, "stale")
    c.imm("0c82", seats.LAST_ID)
    c.branch(2, "stale")
    c.emit("2f02")
    call(c, RAW_LOOKUP, 4)
    c.emit("4a80")
    c.branch(7, "stale")
    c.emit("2840 2014")
    c.imm("0c80", 1)
    c.branch(6, "stale")
    c.emit("2c2c0024")
    c.imm("0c86", 304)
    c.branch(5, "bad")
    c.imm("0c86", 311)
    c.branch(2, "bad")
    # Native snapshot roots use the original generation's canonical key.
    c.imm("41f9", n.SNAP)
    c.emit("7e08")
    c.label("snap")
    c.emit("2010 4a80")
    c.branch(7, "next_snap")
    c.emit("20280010 b082")
    c.branch(7, "frozen")
    c.label("next_snap")
    c.emit("41e80040")
    c.imm("0687", -1)
    c.branch(6, "snap")
    # Restrict the first implementation to all-ONESHOT native kit contexts.
    load(c, KIT)
    c.emit("2040 7e10")
    c.label("machines")
    c.emit("7000 102800d6 4a80")
    c.branch(6, "bad")
    c.emit("41e80450")
    c.imm("0687", -1)
    c.branch(6, "machines")
    c.emit("7e00")
    c.imm("41f9", 0x405B1368)
    c.imm("2279", w.STATE + 68)
    c.label("slots")
    for op in ("2010", "2011"):
        c.emit(op + " b082")
        c.branch(6, "skip_" + op)
        c.emit("2007 b086")
        c.branch(6, "alias")
        c.label("skip_" + op)
    c.emit("41e80010 43e90010")
    c.imm("0687", 1)
    c.imm("0c87", 1024)
    c.branch(6, "slots")
    c.emit("2006 d080 d080 d080 d080")
    c.imm("41f9", 0x405B1368)
    c.emit("d1c0")
    for off in range(0, 16, 4):
        c.emit(f"2028{off:04x} 222c{16 + off:04x} b081")
        c.branch(6, "stale")
    c.emit("2006 d080 d080")
    c.imm("41f9", 0x405B5368)
    c.emit("d1c0 2010")
    c.imm("0c80", 0x10000)
    c.branch(4, "bad")
    c.imm("223c", 52)
    c.emit("4c010800")
    c.imm("2679", 0x405A0F64)
    c.emit("d7c0")
    c.imm("2239", 0x405A0F68)
    c.emit("200b b081")
    c.branch(4, "bad")
    c.emit("202b0030")
    c.imm("0c80", 1)
    c.branch(6, "alias")
    load(c, PHASE)
    c.imm("0c80", 1)
    c.branch(7, "latch")
    for op, field in (
        ("200c", ENTRY),
        ("2006", PRIVATE),
        ("202b0010", START),
        ("202b0014", SIZE),
    ):
        c.emit(op)
        load(c, field, 1)
        c.emit("b081")
        c.branch(6, "stale")
    c.branch(0, "ok")
    c.label("latch")
    c.emit("200c")
    store(c, ENTRY)
    c.emit("2006")
    store(c, PRIVATE)
    for off, field in ((16, START), (20, SIZE)):
        c.emit(f"202b{off:04x}")
        store(c, field)
    c.label("ok")
    c.emit("7000")
    c.branch(0, "return")
    for label, code in (("bad", -1), ("stale", -2), ("frozen", -3), ("alias", -5)):
        c.label(label)
        c.emit(f"{0x7000 | (code & 255):04x}")
        c.branch(0, "return")
    c.label("return")
    c.emit("4cd77cfc 4fef0030 4e75")
    return c.finish(VALIDATE)


def begin():
    c = Code()
    c.emit("4feffff8 48d70404")
    call(c, VALIDATE)
    c.emit("4a80")
    c.branch(6, "return")
    load(c, SEQ)
    c.imm("0c80", -1)
    c.branch(7, "bad")
    c.emit("5280")
    store(c, SEQ)
    c.emit("7000")
    c.imm("23c0", ack.constants()["CF_STATE"] + ack.PHASE)
    c.imm("203c", contract()["constants"]["RTOK"])
    c.imm("23c0", ack.constants()["CF_STATE"] + 56)
    for field in (SIZE, START, SEQ, TOKEN, EPOCH):
        load(c, field)
        c.emit("2f00")
    call(c, ack.CF_REQUEST, 20)
    c.branch(0, "return")
    c.label("bad")
    c.emit("70ff")
    c.label("return")
    c.emit("4cd70404 508f 4e75")
    return c.finish(BEGIN)


def commit():
    c = Code()
    c.emit("4fefffd0 48d77cfc")
    call(c, VALIDATE)
    c.emit("4a80")
    c.branch(6, "return")
    astate = ack.constants()["CF_STATE"]
    c.imm("2039", astate + ack.PHASE)
    c.imm("0c80", 2)
    c.branch(6, "bad")
    for field, off in (
        (EPOCH, ack.EPOCH),
        (TOKEN, ack.GENERATION),
        (SEQ, ack.SEQUENCE),
        (START, ack.START),
        (SIZE, ack.SIZE),
    ):
        load(c, field)
        c.imm("2239", astate + off)
        c.emit("b081")
        c.branch(6, "bad")
    # Atomic final cancellation/tombstone point; stock unload runs at old SR.
    c.emit("40c7 2007")
    c.imm("0080", 0x700)
    c.emit("46c0")
    load(c, CANCEL)
    c.emit("4a80")
    c.branch(6, "cancel_masked")
    # Close the context-switch interval after the long root scan. Sample and
    # FREEZE mutations already hold the same lease; these live context fields
    # and machine selections are rechecked at the atomic tombstone point.
    for actual, field in (
        (n.STATE, EPOCH),
        (0x80004704, KIT),
        (q.CURRENT_TCB, OWNER),
    ):
        c.imm("2039", actual)
        load(c, field, 1)
        c.emit("b081")
        c.branch(6, "cancel_masked")
    for actual, expected in (
        (w.STATE + 12, 3),
        (STATE + PHASE, 3),
        (q.STATE + 56, 0),
        (q.STOCK_BUSY, 0),
        (n.STATE + 24, 0),
    ):
        c.imm("2039", actual)
        c.imm("0c80", expected)
        c.branch(6, "cancel_masked")
    load(c, KIT)
    c.emit("2040 7210")
    c.label("atomic_machines")
    c.emit("7000 102800d6 4a80")
    c.branch(6, "cancel_masked")
    c.emit("41e80450")
    c.imm("0681", -1)
    c.branch(6, "atomic_machines")
    load(c, ENTRY)
    c.emit("2840 7003 2880 7000")
    c.imm("23c0", astate + ack.PHASE)
    c.emit("46c7")
    load(c, PRIVATE)
    c.emit("d080 d080 d080 d080")
    c.imm("2079", w.STATE + 68)
    c.emit("d1c0 70ff 20c0 7000 20c0 20c0 2080 7001")
    c.imm("23c0", n.STATE + 24)
    load(c, PRIVATE)
    c.emit("2f00")
    value(c, ACTIVE_UNLOAD, 1)
    call(c, n.UNLOAD, 4)
    value(c, ACTIVE_UNLOAD, 0)
    c.emit("7000")
    c.imm("23c0", n.STATE + 24)
    load(c, ENTRY)
    c.emit("2f00")
    call(c, seats.CLEAN, 4)
    load(c, SUCCESSES)
    c.emit("5280")
    store(c, SUCCESSES)
    c.emit("7000")
    c.branch(0, "return")
    c.label("cancel_masked")
    c.emit("46c7")
    c.label("bad")
    c.emit("70ff")
    c.label("return")
    c.emit("4cd77cfc 4fef0030 4e75")
    return c.finish(COMMIT)


def lookup_guard():
    c = Code()
    c.imm("2039", w.STATE + 12)
    c.imm("0c80", 3)
    c.branch(6, "stock")
    c.emit("202f0004")
    load(c, TOKEN, 1)
    c.emit("b081")
    c.branch(6, "stock")
    c.emit("7000 4e75")
    c.label("stock")
    c.imm("4ef9", RAW_LOOKUP)
    return c.finish(LOOKUP_GUARD)


def mutation_guard(address, fallback, load_operation):
    c = Code()
    c.emit("4feffff0 48d70c0c")
    call(c, q.ENTER)
    c.imm("2039", w.STATE + 12)
    c.imm("0c80", 3)
    c.branch(6, "legacy")
    load(c, OWNER)
    c.imm("2239", q.CURRENT_TCB)
    c.emit("b081")
    c.branch(6, "deny")
    load(c, PHASE)
    c.imm("0c80", 3)
    c.branch(6, "deny")
    load(c, ACTIVE_UNLOAD)
    c.imm("0c80", 1)
    c.branch(7, "stock")
    c.branch(0, "deny")
    c.label("legacy")
    c.imm("0c80", 2)
    c.branch(6, "stock")
    call(c, q.GATE)
    c.emit("4a80")
    c.branch(6, "deny")
    c.label("stock")
    c.emit("242f0014")
    if load_operation:
        c.emit("262f0018 2f03")
    c.emit("2f02")
    call(c, fallback, 8 if load_operation else 4)
    c.emit("2400")
    c.branch(0, "return")
    c.label("deny")
    c.emit("74ff" if load_operation else "7400")
    c.label("return")
    call(c, q.LEAVE)
    c.emit("2002 4cd70c0c 4fef0010 4e75")
    return c.finish(address)


def driver():
    c = Code()
    c.emit("4feffff0 48d70c0c")
    c.emit("202f0014")
    c.imm("0c80", 0x802)
    c.branch(6, "unknown")
    c.emit("246f0018 45ea00e0 7610")
    c.label("track")
    c.emit("7000 3012")
    c.imm("0c80", 304)
    c.branch(5, "next")
    c.imm("0c80", 311)
    c.branch(3, "deny")
    c.label("next")
    c.emit("45ea0060")
    c.imm("0683", -1)
    c.branch(6, "track")
    c.branch(0, "forward")
    c.label("unknown")
    c.imm("2039", w.STATE + 12)
    c.imm("0c80", 3)
    c.branch(6, "forward")
    c.label("deny")
    value(c, CANCEL, 1)
    load(c, 92)
    c.emit("5280")
    store(c, 92)
    c.emit("70ff")
    c.branch(0, "return")
    c.label("forward")
    c.emit("2f2f0020" * 4)
    call(c, RAW_DRIVER, 16)
    c.label("return")
    c.emit("4cd70c0c 4fef0010 4e75")
    return c.finish(DRIVER)


def receipt_cpu():
    from copy import deepcopy

    original = ack.constants
    cfg = deepcopy(original())
    cfg.update(FRAGMENTS=64, TIMEOUT=512)
    ack.constants = lambda: cfg
    try:
        parts = ack.cpu()
    finally:
        ack.constants = original
    block = parts[ack.CF_REQUEST]
    before, after = bytes.fromhex("202b0010"), bytes.fromhex("202b0038")
    require(block.count(before) == 16, "Completion-domain emitter drift")
    parts[ack.CF_REQUEST] = block.replace(before, after)
    return parts


def receive():
    """Original frame ISR return, matching and one stock GUI timer notification."""
    c = Code()
    c.emit("4fef0010 4feffff0 48d70303")
    call(c, ack.CF_CONSUME)
    c.emit("2200")
    load(c, PHASE)
    c.imm("0c80", 2)
    c.branch(6, "return")
    load(c, 100)
    c.emit("4a80")
    c.branch(6, "return")
    c.emit("4a81")
    c.branch(6, "wake")
    load(c, CANCEL)
    c.emit("4a80")
    c.branch(7, "return")
    c.label("wake")
    # Authenticated stock timer ISR at 0x400c09ec posts this static message.
    # Avoid the stock unbounded queue push when its ring is already full.
    c.imm("2039", 0x40966F40)
    c.imm("2239", 0x40966F4C)
    c.emit("b081")
    c.branch(2, "return")
    value(c, 100, 1)
    c.imm("4879", 0x40240EB8)
    c.imm("4879", 0x40966F3C)
    call(c, 0x40001896, 8)
    c.label("return")
    c.emit("4cd70303 4fef0010")
    c.imm("4ef9", 0x4002DD88)
    return c.finish(loop.RECEIVE)


def payload():
    contract()
    parts = {
        loop.RECEIVE: receive(),
        POLL: poll(),
        QUEUE: queue(),
        MANAGER: q.manager(),
        WORKER: worker(),
        DONE: done(),
        BEGIN: begin(),
        VALIDATE: validate(),
        COMMIT: commit(),
        DRIVER: driver(),
        RAW_DRIVER: DRIVER_BYTES + b"\x4e\xf9" + struct.pack(">I", DRIVER_SITE + 8),
        LOOKUP_GUARD: lookup_guard(),
        RAW_LOOKUP: seats.lookup(),
    }
    for i in range(3):
        parts[GUARDS + i * 256] = mutation_guard(
            GUARDS + i * 256, w.SLOT_GUARDS + i * 256, i == 0
        )
    ordered = sorted(parts.items())
    for (at, code), (next_at, _) in zip(ordered, ordered[1:], strict=False):
        require(at + len(code) <= next_at, "Native retirement payload overlap")
    return parts


def build(output, *, gate_state=None):
    """Compose the unchanged diagnostic with a separate native seal carrier."""
    # isort: off
    from lab import runtime  # initialize pinned import paths
    import sharcldr
    from sharc_selache import compare_listing, find_elf_section, swap_parcels
    from lab import recorder_retirement_gate as gate
    from lab.dsp_build import COMPILER, TOOLS, command
    from lab.sharc_hooks import context_restores, context_stores
    from lab.sharc_tools import assemble, header

    # isort: on
    cfg = contract()
    k = cfg["constants"]
    output.mkdir(exist_ok=False)
    blob, base = seats.build_diagnostic(output / "gate", gate_state=gate_state)
    constants = dict(
        k,
        REQUEST_STATE=observer.constants()["STATE"],
        GATE_STATE=(gate.contract()["constants"]["STATE"] if gate_state is None else gate_state),
        SLOTS=observer.constants()["SLOTS"],
        POOL_START=observer.constants()["POOL_START"],
    )
    (output / "protocol.h").write_text(
        "\n".join(f"#define {name} {v:#x}u" for name, v in constants.items()) + "\n"
    )
    (output / "seal.c").write_bytes((MACHINE / "seal.c").read_bytes())
    command(
        [
            COMPILER,
            "-proc",
            "ADSP-21569",
            "-O1",
            "-S",
            "-o",
            output / "kernel-original.s",
            output / "seal.c",
        ]
    )
    assembly = (output / "kernel-original.s").read_text()
    assembly = re.sub(
        r"(?m)^(\s*R\d+ = R\d+ \+ R\d+;)$", r".NOCOMPRESS;\n\1\n.COMPRESS;", assembly
    )
    (output / "kernel.s").write_text(assembly)

    def symbol(text, name):
        return int(re.search(rf"(?m)^{name}\.:\n\s+([0-9a-f]+)", text)[1], 16)

    observer_fn = symbol(
        (output / "gate/observer/listing.txt").read_text(), "observer_frame"
    )
    gate_fn = symbol((output / "gate/listing.txt").read_text(), "gate_frame")
    scratch, stack = k["DSP_STATE"] + 0x1000, k["DSP_END"] - 0x100

    def invoke(label, function):
        return (
            "M5=0; M6=1; M7=-1; M14=1;\n"
            + " ".join(f"L{i}=0;" for i in range(16))
            + f"\nI7={stack:#x}; I6=I7; R2=I6;\nCJUMP {function} (DB);\n"
            f"DM(I7,M7)=R2; DM(I7,M7)={label}_returned-1;\n{label}_returned:\n"
        )

    text = (
        ".SECTION/PM seg_pmco;\n.EXTERN seal_emit.;\n.GLOBAL seal_hook;\nseal_hook:\n"
    )
    text += context_stores(scratch)
    text += f"R0=ASTATX; DM({scratch + 0x104:#x})=R0; R0=ASTATY; DM({scratch + 0x108:#x})=R0; R0=I4; DM({scratch + 0x120:#x})=R0;\n"
    text += f"R0=DM({constants['REQUEST_STATE']:#x}); R1=DM({k['DSP_STATE']:#x}); COMP(R0,R1); IF NE JUMP run_gates;\n"
    text += f"R0=DM({k['DSP_STATE'] + 4:#x}); R1=0; COMP(R0,R1); IF NE JUMP emit;\nrun_gates:\n"
    text += invoke("observer", f"{observer_fn:#x}") + invoke("gate", f"{gate_fn:#x}")
    text += f"emit:\nR4=DM({scratch + 0x120:#x});\n" + invoke("seal", "seal_emit.")
    text += context_restores(scratch)
    text += f"R0=DM({scratch + 0x108:#x}); ASTATY=R0; R0=DM({scratch + 0x104:#x}); ASTATX=R0; R0=DM({scratch:#x});\nI2=DM(-17,I6); I3=DM(-16,I6); JUMP 0x1c75c9;\n"
    text += ".SECTION/DM seg_dmda;\n.VAR seal_anchor=0;\n"
    (output / "wrapper.s").write_text(text)
    (output / "memory.ldf").write_text("""ARCHITECTURE(ADSP-21569)
MEMORY {
 code { TYPE(BW RAM) START(0x200c0000) END(0x200c7fff) WIDTH(8) }
 data { TYPE(BW RAM) START(0x200f8000) END(0x200f87ff) WIDTH(8) }
}
PROCESSOR core0 { OUTPUT($COMMAND_LINE_OUTPUT_FILE) ENTRY(seal_hook)
 SECTIONS {
 code SW { INPUT_SECTIONS($COMMAND_LINE_OBJECTS(seg_pmco seg_swco seg_l1_block0_swco seg_l1_block1_swco seg_l2_swco)) } > code
 data BW { INPUT_SECTIONS($COMMAND_LINE_OBJECTS(seg_dmda seg_l2 seg_l1_bss seg_l2_bss)) } > data
 }
}
""")
    for stem in ("wrapper", "kernel"):
        command(
            [
                TOOLS / "selas",
                "-proc",
                "ADSP-21569",
                "-o",
                output / f"{stem}.doj",
                output / f"{stem}.s",
            ]
        )
    command(
        [
            TOOLS / "seld",
            "-proc",
            "ADSP-21569",
            "-T",
            output / "memory.ldf",
            "-o",
            output / "seal.dxe",
            output / "wrapper.doj",
            output / "kernel.doj",
        ]
    )
    listing = command([TOOLS / "seldump", "-ns", "code", output / "seal.dxe"])
    (output / "listing.txt").write_text(listing)
    require(
        compare_listing(listing).all_extents_agree, "Seal instruction width mismatch"
    )
    code = swap_parcels(find_elf_section(output / "seal.dxe", "code"))
    data = find_elf_section(output / "seal.dxe", "data")
    require(
        len(code) <= 0x8000 and len(data) <= 0x800 and not any(data),
        "Seal arena overflow",
    )
    raw = bytearray(blob)
    blocks = sharcldr.parse_blocks(raw)
    memory = sharcldr.LoadedMemory.from_stream(raw, blocks)
    for lo, hi in (
        (k["CODE_BASE"], k["CODE_BASE"] + 0x8000),
        (k["DSP_STATE"], k["DSP_END"]),
    ):
        require(
            not any(
                a < hi and b > lo
                for a, b in zip(memory._segments[0], memory._segments[1], strict=True)
            ),
            "Seal arena overlap",
        )
    hook = symbol(listing, "seal_hook")
    off = sharcldr.offset_for_address(blocks, observer.FRAME_SITE)
    before = bytes.fromhex(base["patches"][0]["after"])
    require(raw[off : off + len(before)] == before, "Seal frame hook drift")
    jump = assemble(f".SECTION/PM seg_pmco;\nJUMP {hook:#x};\nNOP;\n").boot_bytes
    require(len(jump) == len(before), "Seal hook extent")
    raw[off : off + len(jump)] = jump
    result = (
        bytes(raw)
        + header(k["CODE_BASE"], len(code))
        + code
        + header(k["DSP_STATE"], k["DSP_END"] - k["DSP_STATE"], fill=0)
    )
    (output / "RETIRE_BLOB.bin").write_bytes(result)
    metadata = dict(
        base=base,
        hook=hook,
        code_bytes=len(code),
        blob_sha256=hashlib.sha256(result).hexdigest(),
        contract_sha256=sha256(MACHINE / "contract.json"),
        stock_blob_sha256=sha256(runtime.STOCK_BLOB),
    )
    write_json(output / "build.json", metadata)
    return result, metadata
