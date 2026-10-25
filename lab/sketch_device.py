"""Isolated OS1.16 Sketch/BUF placement; existing emulator emitters stay intact.

Keep arena-relative offsets so local branches and structure arithmetic retain
their meaning. Relocate only audited long instruction operands and explicitly
classified pointer tables, never a byte-pattern replacement over an image.
This experimental reservation has CPU-emulator evidence, not physical ownership.
"""

import hashlib
import struct
from dataclasses import dataclass

from lab.coldfire import audit_code
from lab.cpu_extension import (
    CAVE,
    GUARD,
    LIMIT,
    MAIN_LIMIT,
    RESET,
    RESET_BYTES,
    Segment,
    loader,
    segment_chain,
)
from lab.dt2_116 import BASE as MAIN_BASE
from lab.dt2_116 import STOCK_SHA
from lab.project import require


@dataclass(frozen=True)
class Arena:
    name: str
    source: int
    size: int
    destination: int


# Separate from the existing 64 KiB Arp/Flex reservation. One guarded interval
# per inherited arena preserves state ABI and avoids a new compacting linker.
START = LIMIT
_SPECS = (
    ("destination", 0x10300000, 0x1000),
    ("generations", 0x10400000, 0x8000),
    ("worker", 0x10600000, 0xB000),
    ("freeze_queue", 0x10700000, 0x4000),
    ("sender", 0x10800000, 0x2000),
    ("receipt", 0x10900000, 0x4000),
    ("receive_loop", 0x10A00000, 0x4000),
    ("disabled_diagnostic", 0x10B00000, 0x4000),
    ("generation_seats", 0x10C00000, 0x4000),
    ("retirement", 0x10D00000, 0x10000),
    ("cleanup", 0x10E00000, 0x4000),
    ("performance", 0x10F00000, 0x4000),
    ("next_bar", 0x11000000, 0x8000),
    ("sketch", 0x11100000, 0x8000),
    ("freeze_source", 0x11200000, 0x4000),
)
_cursor = START
_arenas = []
for _name, _source, _size in _SPECS:
    _arenas.append(Arena(_name, _source, _size, _cursor + 0x100))
    _cursor += _size + 0x200
ARENAS = tuple(_arenas)
END = (_cursor + 4095) & ~4095


def relocate(value):
    for arena in ARENAS:
        if arena.source <= value < arena.source + arena.size:
            return arena.destination + value - arena.source
    # All known synthetic CPU addresses must have an explicit arena owner.
    require(
        not 0x10000000 <= value < 0x11300000, f"Unowned synthetic address {value:#x}"
    )
    return value


def relocate_code(raw, address):
    """The audited subset has at most one long extension per instruction.

    A six-byte instruction contains its long operand at +2. Other forms cannot
    hide a relocatable long: check and reject such an emitter change. Local
    relative branches are preserved by whole-arena placement.
    """
    data, relocations = bytearray(raw), []
    for instruction in audit_code(raw, address):
        off = instruction["address"] - address
        size = len(bytes.fromhex(instruction["bytes"]))
        if size == 6 and instruction["kind"] != "BRANCH":
            value = int.from_bytes(raw[off + 2 : off + 6], "big")
            target = relocate(value)
            if target != value:
                struct.pack_into(">I", data, off + 2, target)
                relocations.append(dict(offset=off + 2, source=value, target=target))
        else:
            for at in range(off + 2, off + size - 3, 2):
                value = int.from_bytes(raw[at : at + 4], "big")
                require(relocate(value) == value, "Unreviewed long operand placement")
    audit_code(data, relocate(address))
    return bytes(data), relocations


class Overlay:
    def __init__(self, stock):
        require(
            hashlib.sha256(stock).hexdigest() == STOCK_SHA,
            "Sketch needs exact OS1.16 MAIN",
        )
        self.stock, self.parts, self.hooks = stock, {}, {}

    def put(self, at, raw, label, kind="code"):
        require(
            raw and kind in ("code", "stock-trampoline", "data", "pointers"),
            "Invalid payload",
        )
        # An overlay may replace an entry, never silently overlap its neighbor.
        for other, (data, _, _) in self.parts.items():
            require(
                other == at or at + len(raw) <= other or at >= other + len(data),
                f"Payload overlap {label}",
            )
        self.parts[at] = (raw, label, kind)

    def group(self, parts, owner):
        for at, raw in parts.items():
            self.put(at, raw, f"{owner}/{at:#x}")

    def jump(self, at, expected, target, label):
        require(len(expected) >= 6 and len(expected) % 2 == 0, "Hook extent")
        require(
            self.stock[at - MAIN_BASE : at - MAIN_BASE + len(expected)] == expected,
            f"Sketch stock hook drift: {label}",
        )
        require(at not in self.hooks, f"Duplicate hook {label}")
        raw = (
            b"\x4e\xf9"
            + struct.pack(">I", target)
            + b"\x4e\x71" * ((len(expected) - 6) // 2)
        )
        self.hooks[at] = (expected, raw, label)


def compose(
    stock, *, arm_diagnostics=False, clock_fix=False, operation_diagnostics=False
):
    """Final native install graph of SketchUI; no Machine or host job execution."""
    from lab import buf_auto_retirement as auto
    from lab import buf_freeze as bf
    from lab import buf_next_bar as nb
    from lab import buf_performance as perf
    from lab import recorder_ack_loop as loop
    from lab import recorder_destination as dest
    from lab import recorder_dsp_reuse as paused
    from lab import recorder_freeze_code as n
    from lab import recorder_freeze_worker_code as q
    from lab import recorder_native_retirement as t
    from lab import recorder_retirement as obs
    from lab import recorder_seat_reuse as seats
    from lab import recorder_worker_code as w
    from lab import sketch as s

    normal = dest

    o = Overlay(stock)
    o.put(dest.LABEL, b"DEST\0", "destination/label", "data")
    o.put(
        dest.TABLE,
        struct.pack(">5I", *(dest.ARENA + 0x110 + i * 8 for i in range(5))),
        "destination/table",
        "pointers",
    )
    for i, name in enumerate(("NORMAL", "BUF 1", "BUF 2", "BUF 3", "BUF 4")):
        o.put(
            dest.ARENA + 0x110 + i * 8,
            name.encode() + b"\0",
            f"destination/name{i}",
            "data",
        )
    o.group(
        {
            dest.DRAW: dest.cell(),
            dest.SET: dest.setter(),
            dest.ROTATE: dest.rotation(),
            normal.FILTER: normal.allocation_filter(),
        },
        "destination",
    )
    o.put(normal.RESERVED, b"\xff" * 52, "destination/reservations", "data")
    o.jump(0x400209AE, bytes.fromhex("487800052f02"), dest.ROTATE, "destination/rotate")
    o.jump(0x400221A0, bytes.fromhex("487800014878002f"), dest.DRAW, "destination/draw")
    o.jump(
        normal.SEARCH_SITE,
        normal.SEARCH_BYTES,
        normal.FILTER,
        "destination/reserved-search",
    )

    parts, originals = n.payload()
    for i, (op, (pc, _)) in enumerate(n.RESOURCE_SITES.items()):
        o.jump(pc, originals[pc], w.DISPATCH + i * 256, "resource/" + op)
    for i, pc in enumerate((n.SAVE, n.LOAD_PROJECT)):
        before = stock[pc - MAIN_BASE : pc - MAIN_BASE + 8]
        tramp, guard = n.TRAMPOLINES + 0x700 + i * 32, n.GUARDS + i * 256
        parts[tramp] = before + b"\x4e\xf9" + struct.pack(">I", pc + 8)
        parts[guard] = n.project_guard(guard, tramp)
        o.jump(pc, before, guard, "volatile-project-guard/" + str(i))
    for i, pc in enumerate((0x40154540, n.UNLOAD, n.CLEAR)):
        before = stock[pc - MAIN_BASE : pc - MAIN_BASE + 8]
        tramp = n.TRAMPOLINES + 0x800 + i * 32
        parts[tramp] = before + b"\x4e\xf9" + struct.pack(">I", pc + 8)
        o.jump(pc, before, t.GUARDS + i * 256, "slot-guard/" + str(i))
    o.group(parts, "generations")
    o.put(n.STATE, struct.pack(">I", 1), "generations/epoch", "data")
    o.put(n.GEN_NAME, b"/TEMP/BUF-GEN\0".ljust(32, b"\0"), "generations/name", "data")
    for buf in range(4):
        for serial in range(8):
            o.put(
                n.NAMES + (buf * 8 + serial) * 32,
                f"/TEMP/B{buf + 1}-{serial + 1:03d}".encode().ljust(32, b"\0"),
                f"generations/frozen-name-{buf}-{serial}",
                "data",
            )
    o.group(w.payload(), "worker")
    finish_raw, _, _ = o.parts.pop(w.FINISH)
    require(finish_raw[24:32] == bytes(8), "Worker FINISH padding drift")
    o.put(w.FINISH, finish_raw[:24], "worker/finish-dispatch")
    o.put(w.FINISH + 32, finish_raw[32:], "worker/finish-body")
    for i, (name, text) in enumerate(w.f.USE_ERRORS.items()):
        text = (
            "BUF: SESSION LIMIT" if name == "limit" else text.replace("FLEX:", "BUF:")
        )
        o.put(
            w.ERROR_NAMES + i * 64,
            text.encode().ljust(64, b"\0"),
            "worker/error/" + name,
            "data",
        )
    o.put(
        w.ERROR_TABLE,
        struct.pack(
            ">" + "I" * len(w.ERRORS),
            *(w.ERROR_NAMES + i * 64 for i in range(len(w.ERRORS))),
        ),
        "worker/errors",
        "pointers",
    )
    o.jump(0x40021986, bytes.fromhex("487940229675"), w.ERROR_ENTRY, "worker/error")
    o.jump(0x400CD638, bytes.fromhex("4feffff448d70c04"), w.PAGE_FILTER, "worker/page")
    for pc, (before, target) in w.HOOKS.items():
        o.jump(pc, bytes.fromhex(before), target, "worker/entry/" + hex(pc))
    require(
        not operation_diagnostics or (arm_diagnostics and not clock_fix),
        "Operation diagnostics require ARM diagnostics and a separate clock profile",
    )
    o.group(q.payload(operation_diagnostics=operation_diagnostics), "freeze-queue")
    o.put(q.LABEL, b"FREEZE\0", "freeze-queue/label", "data")
    o.group(loop.cpu(), "receive-loop")
    o.group(seats.payload(), "generation-seats")
    o.group(t.payload() | t.receipt_cpu(), "retirement")
    sender = obs.sender()
    for old, new in ((n.FIRST_ID, seats.FIRST_ID), (n.FIRST_ID + 7, seats.LAST_ID)):
        require(sender.count(struct.pack(">I", old)) == 1, "Sender bounds drift")
        sender = sender.replace(struct.pack(">I", old), struct.pack(">I", new))
    o.put(obs.CF_ENTRY, sender, "retirement/sender")
    o.put(paused.ENTRY, bytes.fromhex("70ff4e75"), "retirement/disabled-paused-command")
    o.put(t.LABEL, b"RETIRE\0", "retirement/label", "data")
    o.put(
        n.LOOKUP,
        b"\x4e\xf9" + struct.pack(">I", t.LOOKUP_GUARD),
        "retirement/lookup-gate",
    )
    o.jump(loop.RECEIVE_SITE, loop.RECEIVE_BYTES, loop.RECEIVE, "retirement/receive")
    o.jump(t.DRIVER_SITE, t.DRIVER_BYTES, t.DRIVER, "retirement/driver")
    o.group(auto.payload(), "cleanup")
    o.group(perf.payload(), "performance")
    o.put(q.SUBMIT, b"\x4e\xf9" + struct.pack(">I", perf.SUBMIT), "performance/submit")
    require(not clock_fix or arm_diagnostics, "Clock fix requires diagnostics")
    o.group(
        nb.payload(
            arm_diagnostics=arm_diagnostics,
            clock_fix=clock_fix,
            operation_diagnostics=operation_diagnostics,
        ),
        "next-bar",
    )
    o.put(nb.STATE + nb.ENABLED, struct.pack(">I", 1), "next-bar/enabled", "data")
    o.put(nb.LABEL, b"BUF AUTO USE\0", "next-bar/label", "data")
    o.put(perf.KEY, nb.key_bridge(), "next-bar/key")
    o.put(w.WORKER, seats.worker(require_track=False), "next-bar/worker")
    o.put(w.ASSIGN, w.assign(assign_track=False), "next-bar/publication")
    o.put(perf.ELIGIBLE, perf.eligible(all_oneshot=False), "next-bar/eligibility")
    o.jump(nb.ARM_SITE, nb.ARM_BYTES, nb.ARM, "next-bar/arm")
    o.jump(nb.CLOCK_SITE, nb.CLOCK_BYTES, nb.IRQ, "next-bar/clock")
    o.jump(q.GUI, q.GUI_BYTES, nb.POLL, "next-bar/poll")
    o.put(w.ENTRY, b"\x4e\xf9" + struct.pack(">I", nb.USE_GATE), "sketch/use-gate")
    o.group(bf.payload(), "freeze-source")
    o.put(q.GATE, b"\x4e\xf9" + struct.pack(">I", bf.GATE), "freeze-source/gate")
    o.put(q.DONE, b"\x4e\xf9" + struct.pack(">I", bf.DONE), "freeze-source/done")
    o.put(s.STATE + s.BUF, struct.pack(">I", 1), "sketch/selection", "data")
    pointer_tables = {s.TEXTS, s.VTABLE - 8, s.SHARED, s.SHARED + 0x50}
    for at, raw in s.payload(
        stock,
        arm_enabled=True,
        freeze_enabled=True,
        arm_diagnostics=arm_diagnostics,
        clock_fix=clock_fix,
        operation_diagnostics=operation_diagnostics,
    ).items():
        kind = (
            "pointers"
            if at in pointer_tables
            else "data"
            if s.STRINGS <= at < s.LINE
            else "code"
        )
        o.put(at, raw, "sketch/" + hex(at), kind)
    o.jump(perf.KEY_SITE, perf.KEY_BYTES, s.KEY, "sketch/key")
    o.jump(s.MAIN_SITE, s.MAIN_BYTES, s.MAIN_KEY, "sketch/main-key")
    o.jump(s.ROUTE_SITE, bytes.fromhex("4fefffa048d77cfc"), s.ROUTE, "sketch/route")
    o.put(
        n.FREEZE,
        b"\x4e\xf9" + struct.pack(">I", w.FREEZE_GUARD) + b"\x4e\x71",
        "worker/freeze-guard",
    )
    for at, (raw, label, _kind) in list(o.parts.items()):
        if (
            n.TRAMPOLINES <= at < n.GUARDS
            or w.TRAMP <= at < w.TRAMP + 0x100
            or at in (q.TRAMP, t.RAW_DRIVER, s.MAIN_KEY + 0x80)
        ):
            # Prefix bytes came from authenticated stock; only the appended
            # JMP belongs to this emitter's independently audited ISA subset.
            require(raw[-6:-4] == b"\x4e\xf9", "Stock trampoline tail")
            require(
                not any(
                    0x10000000 <= int.from_bytes(raw[i : i + 4], "big") < 0x11300000
                    for i in range(0, len(raw) - 9, 2)
                ),
                "Synthetic stock prefix",
            )
            o.put(at, raw, label, "stock-trampoline")
    return o


def build(
    stock, *, arm_diagnostics=False, clock_fix=False, operation_diagnostics=False
):
    overlay = compose(
        stock,
        arm_diagnostics=arm_diagnostics,
        clock_fix=clock_fix,
        operation_diagnostics=operation_diagnostics,
    )
    images = {a.name: bytearray(a.size) for a in ARENAS}
    writes, fixes = [], []
    for at, (raw, label, kind) in sorted(overlay.parts.items()):
        arena = next((a for a in ARENAS if a.source <= at < a.source + a.size), None)
        require(
            arena is not None and at + len(raw) <= arena.source + arena.size,
            "Arena overflow " + label,
        )
        if kind == "stock-trampoline":
            tail, relocations = relocate_code(raw[-6:], at + len(raw) - 6)
            data = raw[:-6] + tail
            relocations = [
                dict(r, offset=r["offset"] + len(raw) - 6) for r in relocations
            ]
        elif kind == "code":
            data, relocations = relocate_code(raw, at)
        elif kind == "pointers":
            require(len(raw) % 4 == 0, "Pointer table alignment")
            data, relocations = bytearray(raw), []
            for off in range(0, len(raw), 4):
                value = int.from_bytes(raw[off : off + 4], "big")
                target = relocate(value)
                if target != value:
                    struct.pack_into(">I", data, off, target)
                    relocations.append(dict(offset=off, source=value, target=target))
            data = bytes(data)
        else:
            data, relocations = raw, []
        images[arena.name][at - arena.source : at - arena.source + len(data)] = data
        writes.append(
            dict(
                address=relocate(at),
                source_address=at,
                after=data.hex(),
                label=label,
                kind=kind,
            )
        )
        fixes.extend(
            dict(label=label, address=relocate(at) + r["offset"], **r)
            for r in relocations
        )
    segments, guards = [], []
    for arena in ARENAS:
        data = bytes(images[arena.name])
        used = (len(data.rstrip(b"\0")) + 3) & ~3
        segments.extend(
            (
                Segment(arena.destination - 0x100, GUARD),
                Segment(arena.destination, data[:used], arena.size - used),
                Segment(arena.destination + arena.size, GUARD),
            )
        )
        guards.extend(
            (
                [arena.destination - 0x100, len(GUARD)],
                [arena.destination + arena.size, len(GUARD)],
            )
        )
    chain = segment_chain(segments, reservation=(START, END))
    image = bytearray(stock)
    hooks = []
    for at, (expected, raw, label) in sorted(overlay.hooks.items()):
        data, relocations = relocate_code(raw, at)
        image[at - MAIN_BASE : at - MAIN_BASE + len(data)] = data
        hooks.append(
            dict(
                address=at,
                before=expected.hex(),
                after=data.hex(),
                label=label,
                kind="code",
            )
        )
        fixes.extend(
            dict(label=label, address=at + r["offset"], **r) for r in relocations
        )
    reset_loader = loader(MAIN_BASE + len(stock))
    for at, expected, data, label in (
        (CAVE, bytes(len(reset_loader)), reset_loader, "reset/loader"),
        (
            RESET,
            RESET_BYTES,
            b"\x4e\xb9" + struct.pack(">I", CAVE) + b"\x4e\x71",
            "reset/hook",
        ),
    ):
        require(
            image[at - MAIN_BASE : at - MAIN_BASE + len(expected)] == expected,
            "Reset guard " + label,
        )
        image[at - MAIN_BASE : at - MAIN_BASE + len(data)] = data
        hooks.append(
            dict(
                address=at,
                before=expected.hex(),
                after=data.hex(),
                label=label,
                kind="code",
            )
        )
    image.extend(chain)
    require(len(image) <= MAIN_LIMIT, "Sketch MAIN staging ceiling")
    require(
        image[0x40312000 - MAIN_BASE : len(stock)] == stock[0x40312000 - MAIN_BASE :],
        "SRAM reset source changed",
    )
    metadata = dict(
        firmware="Digitakt II OS1.16",
        profile="isolated-sketch-buf",
        hardware_ready=False,
        stock_sha256=STOCK_SHA,
        sha256=hashlib.sha256(image).hexdigest(),
        reservation=[START, END],
        reservation_bytes=END - START,
        arenas=[vars(a) for a in ARENAS],
        guards=guards,
        relocations=fixes,
        payload_bytes=sum(len(bytes.fromhex(w["after"])) for w in writes),
        initialized_bytes=sum(len(s.data) for s in segments),
        bss_bytes=sum(s.bss for s in segments),
        appended_bytes=len(chain),
        chain_address=MAIN_BASE + len(stock),
        main_bytes=len(image),
        segments=[
            dict(
                destination=s.destination,
                data_bytes=len(s.data),
                bss=s.bss,
                sha256=hashlib.sha256(s.data).hexdigest(),
            )
            for s in segments
        ],
        hooks=hooks,
        writes=writes,
        limits=[
            "Experimental DDR ownership; physical cache/DMA/stack behavior unverified",
            "Isolated profile; cannot compose with existing Flex/Arp/Plaits patch hooks",
            "Prepared recorder input and DSP transport differ from physical startup",
            "NORMAL ready label retains stock SAVE; BUF ready label is not dynamically changed",
        ],
    )
    if arm_diagnostics:
        metadata["arm_diagnostics"] = True
    if clock_fix:
        metadata["clock_fix"] = True
    if operation_diagnostics:
        metadata["operation_diagnostics"] = True
    return bytes(image), metadata
