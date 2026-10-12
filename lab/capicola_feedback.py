"""Exact OS1.16 reply-to-caption overlay; native page-open feedback only.

The existing SRC caption is cached. Reopening SRC refreshes this caption;
this module does not claim continuous screen updates or authorize playback.
"""

import hashlib
import struct

from lab.coldfire import audit_code
from lab.flex_native import Code
from lab.project import require

BASE = 0x40000400
BASE_SHA = "82b17a4f9068f47bef1b272205e3dc153e057fdb67a52db6a9726e5f09ceb8da"
REPLY_WORD = 0x800048A6
HINT = 0x400DA594
WIDTH = 0x40016E58
# Audited OS1.16 zero intervals; do not compose with managed Flex ownership.
GAPS = (
    (0x402FCC5C, 0x402FCD34),
    (0x402FCA98, 0x402FCB5C),
    (0x40301B18, 0x40301BDC),
    (0x403020DC, 0x40302134),
    (0x402FC718, 0x402FC75C),
)
TEXT = (
    "",
    "EMPTY",
    "FORMAT",
    "P<25%",
    "WAIT",
    "READY",
    "ERROR",
    "P<50%",
    "P<75%",
    "P<100%",
)


def hint(address, table, original):
    """D0/D1/A0/A1 are caller scratch; preserve all callee-saved registers."""
    c = Code()
    c.emit("202f0004")
    c.imm("0c80", 8)
    c.branch(6, "stock")
    c.emit("7000")
    c.imm("3039", REPLY_WORD)
    c.emit("2200")
    c.imm("0281", 0xFC00)
    c.imm("0c81", 0xD400)
    c.branch(6, "neutral")
    c.emit("2200 ee89")  # LSR.L #7,D1
    c.imm("0281", 7)
    c.imm("0280", 127)
    c.imm("0c80", 100)
    c.branch(2, "neutral")
    c.imm("0c81", 3)
    c.branch(7, "preparing")
    c.imm("0c81", 5)
    c.branch(7, "ready")
    c.emit("4a80")
    c.branch(6, "neutral")
    c.imm("0c81", 1)
    c.branch(5, "neutral")
    c.imm("0c81", 6)
    c.branch(2, "neutral")
    c.branch(0, "lookup")
    c.label("ready")
    c.imm("0c80", 100)
    c.branch(6, "neutral")
    c.branch(0, "lookup")
    c.label("preparing")
    for ceiling, index in ((25, 3), (50, 7), (75, 8)):
        c.imm("0c80", ceiling)
        c.branch(5, "bucket" + str(index))
    c.emit("7209")
    c.branch(0, "lookup")
    for index in (3, 7, 8):
        c.label("bucket" + str(index))
        c.emit(f"{0x7200 | index:04x}")
        c.branch(0, "lookup")
    c.label("neutral")
    c.emit("7200")
    c.label("lookup")
    c.emit("2001 d080 d080")
    c.imm("43f9", table)
    c.emit("d3c0 2011 4e75")
    c.label("stock")
    c.imm("4ef9", original)
    return c.finish(address)


def caption_width(address):
    """Fit CAPICOLA + its status into the110-pixel native caption area."""
    c = Code()
    c.emit("2f00 2052 2228fff4")  # preserve hint length; A2 is title string
    c.imm("0c81", 8)
    c.branch(6, "stock")
    c.emit("2210")
    c.imm("0c81", int.from_bytes(b"CAPI", "big"))
    c.branch(6, "stock")
    c.emit("22280004")
    c.imm("0c81", int.from_bytes(b"COLA", "big"))
    c.branch(6, "stock")
    c.emit("7212")
    c.branch(0, "done")
    c.label("stock")
    c.emit("721a")
    c.label("done")
    c.emit("9283 2601 201f 4e75")
    return c.finish(address)


def patch_cpu(image):
    require(
        hashlib.sha256(image).hexdigest() == BASE_SHA,
        "Unknown Capicola feedback baseline",
    )
    data, gaps, writes = bytearray(image), [list(g) for g in GAPS], []
    for lo, hi in gaps:
        require(not any(image[lo - BASE : hi - BASE]), "Occupied feedback padding")

    def put(a, b, label, kind="data"):
        before = bytes(data[a - BASE : a - BASE + len(b)])
        data[a - BASE : a - BASE + len(b)] = b
        writes.append(
            dict(
                address=a,
                before=before.hex(),
                after=b.hex(),
                label=label,
                kind=kind,
                instructions=audit_code(b, a) if kind == "code" else [],
            )
        )

    def allocate(b, label, kind="data"):
        options = [(hi - lo, i) for i, (lo, hi) in enumerate(gaps) if hi - lo >= len(b)]
        require(bool(options), f"Feedback padding exhausted: {label} ({len(b)} bytes)")
        _, i = min(options)
        a = gaps[i][0]
        put(a, b, label, kind)
        gaps[i][0] = (a + len(b) + 3) & ~3
        return a

    def change(a, before, after, label):
        require(
            bytes(data[a - BASE : a - BASE + len(before)]) == before
            and len(before) == len(after),
            f"Feedback byte guard: {label}",
        )
        put(a, after, label, "code")

    pointers = []
    for text in TEXT:
        raw = text.encode("ascii")
        pointers.append(
            allocate(
                struct.pack(">IIi", len(raw), len(raw), -1) + raw + b"\0",
                "feedback string " + repr(text),
            )
            + 12
        )
    table = allocate(struct.pack(">10I", *pointers), "feedback strings")
    displaced = bytes.fromhex("7208 202f0004")
    original = allocate(
        displaced + bytes.fromhex("4ef9") + struct.pack(">I", HINT + 6),
        "original hint trampoline",
        "code",
    )
    # Sizes do not depend on locations. Guard/audit code both before and after placement.
    getter = allocate(hint(0, table, original), "status hint", "code")
    put(getter, hint(getter, table, original), "linked status hint", "code")
    width = allocate(caption_width(0), "Capicola caption width", "code")
    put(width, caption_width(width), "linked caption width", "code")
    change(
        HINT,
        displaced,
        bytes.fromhex("4ef9") + struct.pack(">I", getter),
        "hint dispatch",
    )
    change(
        WIDTH,
        bytes.fromhex("721a 9283 2601"),
        bytes.fromhex("4eb9") + struct.pack(">I", width),
        "caption width",
    )
    covered = set()
    for w in writes:
        covered.update(
            range(
                w["address"] - BASE,
                w["address"] - BASE + len(bytes.fromhex(w["after"])),
            )
        )
    require(
        all(
            x == y or i in covered
            for i, (x, y) in enumerate(zip(image, data, strict=True))
        ),
        "Undeclared feedback MAIN change",
    )
    result = bytes(data)
    return result, dict(
        sha256=hashlib.sha256(result).hexdigest(),
        writes=writes,
        hint=getter,
        width=width,
        pointers=pointers,
        reply_word=REPLY_WORD,
        refresh="SRC page open; cached between page opens",
        hardware_verified=False,
    )
