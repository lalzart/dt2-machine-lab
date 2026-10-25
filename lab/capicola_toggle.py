"""Optional OS1.16 CAPI metadata and informational feedback overlay.

The disabled layer is identity. Appended data initializes an unused SRAM tail;
native reset clears the external source after copying. Device ownership is a
separate gate. Existing Flex/Plaits state and initialized SRAM are preserved.
"""

import hashlib
import struct

from lab.coldfire import audit_code
from lab.emit import Code
from lab.project import require

BASE = 0x40000400
BASE_SHA = "0bd3c2989665ec5151d5b14d9fbe3d55ee1810b3698fc2d34e7a1f9daaea5531"
SOURCE_ARENA = 0x40320000
ARENA = 0x8000F180
LIMIT = 0x80010000
PARAM = 204
TABLE = 0x4020F18C
HINT = 0x400DA594
DRAW = 0x40016EC8
RX_CALL = 0x4002DD74
RX_DRIVER = 0x400CD2BC
RX_WORD = 0x800048A6
STATES = ("?", "WAIT", "READY", "CAPI", "STOCK", "MIX", "UNSUP", "OFF")
TITLES = tuple(("STRETCH " + text).ljust(18) for text in STATES)


def requested(raw):
    return 128 <= raw <= 256


def decode_reply(word):
    if word & 0xF000 != 0xD000 or word & 255 > 6:
        return None
    return (word >> 8) & 15, word & 255


def value_formatter(address):
    c = Code()
    c.emit("202f0004 206f0008")
    c.imm("0c80", 128)
    c.branch(5, "off")
    c.imm("0c80", 256)
    c.branch(2, "off")
    c.imm("20bc", int.from_bytes(b"ON\0\0", "big"))
    c.emit("7002 4e75")
    c.label("off")
    c.imm("20bc", int.from_bytes(b"OFF\0", "big"))
    c.emit("7003 4e75")
    return c.finish(address)


def observer(address, cache):
    c = Code()
    c.emit("2f02 7410")
    c.imm("41f9", cache + 16)
    c.label("age")
    c.emit("7000 1010 4a80")
    c.branch(7, "next")
    c.emit("5380 1080")
    c.label("next")
    c.emit("5288 5382")
    c.branch(6, "age")
    c.emit("7000")
    c.imm("3039", RX_WORD)
    c.emit("2200")
    c.imm("0281", 0xF000)
    c.imm("0c81", 0xD000)
    c.branch(6, "invalid")
    c.emit("2200")
    c.imm("0281", 255)
    c.imm("0c81", 6)
    c.branch(2, "invalid")
    c.imm("0280", 0xF00)
    c.emit("e080")
    c.imm("41f9", cache)
    c.emit("d1c0 1081")
    c.imm("41f9", cache + 16)
    c.emit("d1c0 7020 1080")
    c.branch(0, "done")
    c.label("invalid")
    c.imm("41f9", cache)
    c.emit("7408 7000")
    c.label("clear")
    c.emit("20c0 5382")
    c.branch(6, "clear")
    c.label("done")
    c.emit("241f 4e75")
    return c.finish(address)


def receiver(address, watch):
    c = Code()
    c.emit("4feffff0")
    for src, dst in ((20, 0), (24, 4), (28, 8), (32, 12)):
        c.emit(f"202f{src:04x} 2f40{dst:04x}")
    c.imm("4eb9", RX_DRIVER)
    c.emit("4fef0010 4feffff0 48d70303 40c0 2f00")
    c.imm("4eb9", watch)
    c.emit("201f 44c0 4cd70303 4fef0010 4e75")
    return c.finish(address)


def refresh(address, cache, titles):
    c = Code()
    c.emit("4fefffe4 48d70b0f 2012")
    c.imm("0c80", 0x401ED888)
    c.branch(6, "done")
    c.emit("202a0064")
    c.imm("0c80", 2)
    c.branch(6, "done")
    c.emit("2f2a0074")
    c.imm("4eb9", 0x4004ABE8)
    c.emit("588f")
    c.imm("0c80", 15)
    c.branch(2, "done")
    c.emit("2400")
    c.imm("223c", 0x9A)
    c.emit("4c010800")
    c.imm("41f9", 0x80003CD0)
    c.emit("d1c0 7000 1010")
    c.imm("0c80", 2)
    c.branch(6, "done")
    c.emit("2002")
    c.imm("223c", 0x8E)
    c.emit("4c010800")
    c.imm("41f9", 0x80003398)
    c.emit("d1c0 7600 3610 2002")
    c.imm("41f9", cache)
    c.emit("d1c0 7200 1210")
    c.imm("41f9", cache + 16)
    c.emit("d1c0 7000 1010 4a80")
    c.branch(6, "known")
    c.emit("7200")
    c.label("known")
    c.imm("0c81", 6)
    c.branch(3, "range_ok")
    c.emit("7200")
    c.label("range_ok")
    c.imm("0c81", 2)
    c.branch(3, "idle")
    c.imm("0c81", 6)
    c.branch(6, "lookup")
    c.label("idle")
    c.imm("0c83", 128)
    c.branch(5, "off")
    c.imm("0c83", 256)
    c.branch(3, "lookup")
    c.label("off")
    c.emit("7207")
    c.label("lookup")
    c.emit("2001 d080 d080")
    c.imm("43f9", titles)
    c.emit("d3c0 2649 2251 206a006c 20680048 2028fff4")
    c.imm("0c80", 18)
    c.branch(6, "update")
    for off in (0, 4, 8, 12, 16):
        if off == 16:
            c.emit("7000 7200")
        c.emit(("3028" if off == 16 else "2028") + f"{off:04x}")
        c.emit(("3229" if off == 16 else "2229") + f"{off:04x}")
        c.emit("b081")
        c.branch(6, "update")
    c.branch(0, "done")
    c.label("update")
    c.emit("2f0b 2f2a006c")
    c.imm("4eb9", 0x4005B1E0)
    c.emit("508f")
    c.label("done")
    c.emit("4cd70b0f 4fef001c")
    c.imm("4ef9", 0x4005B076)
    return c.finish(address)


def patch_cpu(image, *, enabled=True):
    if not enabled:
        return image, {"enabled": False, "writes": []}
    require(hashlib.sha256(image).hexdigest() == BASE_SHA, "Unknown CAPI CPU baseline")
    require(BASE + len(image) == 0x4031FF60, "Unexpected MAIN extent")
    data = bytearray(image) + bytes(SOURCE_ARENA - BASE - len(image))
    writes = []

    def allocate(payload, label, kind="data", mutable=False):
        while (BASE + len(data)) % 4:
            data.append(0)
        source_address = BASE + len(data)
        address = ARENA + source_address - SOURCE_ARENA
        raw = payload(address) if callable(payload) else payload
        require(address + len(raw) <= LIMIT, "CAPI CPU arena overflow")
        data.extend(raw)
        writes.append(
            dict(
                address=source_address,
                runtime_address=address,
                before=bytes(len(raw)).hex(),
                after=raw.hex(),
                label=label,
                kind=kind,
                mutable=mutable,
            )
        )
        if kind == "code":
            audit_code(raw, address)
        return address

    def change(address, before, after, label, kind="code"):
        off = address - BASE
        require(
            data[off : off + len(before)] == before and len(before) == len(after),
            "CAPI byte guard: " + label,
        )
        data[off : off + len(after)] = after
        writes.append(
            dict(
                address=address,
                before=before.hex(),
                after=after.hex(),
                label=label,
                kind=kind,
                mutable=False,
            )
        )
        if kind == "code":
            audit_code(after, address)

    cache = allocate(bytes(32), "CAPI diagnostic cache", mutable=True)
    labels = allocate(b"Capi\0CAPI\0", "CAPI labels")
    full, short = struct.unpack_from(">2I", image, 0x403119C4 + 24 - BASE)
    fields = (221, 222, PARAM, 223, 224, 225, 226, 227, 10)
    descriptor = allocate(
        struct.pack(">11I", full, short, *fields), "STRETCH CAPI descriptor"
    )
    dispatch = allocate(
        bytes.fromhex("202f0004 0c8000000002 6608 203c")
        + struct.pack(">I", descriptor)
        + bytes.fromhex("4e75 4ef9403117c4"),
        "STRETCH descriptor dispatch",
        "code",
    )
    fmt = allocate(value_formatter, "CAPI OFF/ON formatter", "code")
    pointers = [
        allocate(struct.pack(">IIi", 18, 18, -1) + t.encode() + b"\0", "SRC title " + t)
        + 12
        for t in TITLES
    ]
    table = allocate(struct.pack(">8I", *pointers), "SRC title pointers")
    watch = allocate(lambda a: observer(a, cache), "CAPI reply observer", "code")
    receive = allocate(lambda a: receiver(a, watch), "CAPI RX wrapper", "code")
    draw = allocate(lambda a: refresh(a, cache, table), "CAPI SRC refresh", "code")
    change(
        0x400C8840,
        bytes.fromhex("4ef9403117c4"),
        bytes.fromhex("4ef9") + struct.pack(">I", dispatch),
        "CAPI descriptor lookup",
    )
    change(
        RX_CALL,
        bytes.fromhex("4eb9400cd2bc"),
        bytes.fromhex("4eb9") + struct.pack(">I", receive),
        "CAPI reply observation",
    )
    change(
        DRAW,
        bytes.fromhex("4eb94005b076"),
        bytes.fromhex("4eb9") + struct.pack(">I", draw),
        "CAPI SRC status draw",
    )
    row = TABLE + PARAM * 60
    for off, before, after, label in (
        (12, 32512, 256, "CAPI maximum"),
        (40, None, labels, "CAPI long name"),
        (44, None, full, "CAPI owner caption"),
        (48, None, labels + 5, "CAPI short name"),
        (52, 0x400E1424, fmt, "CAPI formatter"),
    ):
        old = struct.unpack_from(">I", image, row + off - BASE)[0]
        require(before is None or old == before, "CAPI row guard: " + label)
        change(
            row + off, struct.pack(">I", old), struct.pack(">I", after), label, "data"
        )
    # Copy the appended payload into internal SRAM before the original external
    # clear. Original initialized data and both SRAM clear bounds stay intact.
    while (BASE + len(data)) % 4:
        data.append(0)
    change(
        0x40000498,
        bytes.fromhex("b5fc4031ff60"),
        bytes.fromhex("b5fc") + struct.pack(">I", BASE + len(data)),
        "CAPI SRAM initialization copy end",
    )
    result = bytes(data)
    return result, dict(
        enabled=True,
        sha256=hashlib.sha256(result).hexdigest(),
        writes=writes,
        descriptor=descriptor,
        fields=fields,
        formatter=fmt,
        observer=watch,
        receiver=receive,
        refresh=draw,
        cache=cache,
        title_pointers=pointers,
        arena_start=ARENA,
        arena_end=ARENA + len(result) - (SOURCE_ARENA - BASE),
        source_arena_start=SOURCE_ARENA,
        source_arena_end=BASE + len(result),
        cpu_added_bytes=len(result) - len(image),
        latch="next native trigger",
        default="OFF",
        hardware_ready=False,
    )
