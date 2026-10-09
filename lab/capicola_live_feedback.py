"""Native slot-correlated SRC feedback on the OS1.16 UI draw path."""

import hashlib
import struct

from lab.capicola_feedback import BASE, BASE_SHA, GAPS, HINT, TEXT, WIDTH, caption_width
from lab.coldfire import audit_code
from lab.flex_native import Code
from lab.project import require

REPLY_WORD = 0x800048A6
SAMPLE_WORD = 0x80005428
DRAW = 0x40016EC8
EXTRA_GAPS = (
    (0x40301CDC, 0x40301DB4),
    (0x402FC85C, 0x402FC8A8),
    (0x40301F98, 0x40301FDC),
)
TITLES = tuple("CAPICOLA" + " " * (10 - len(t)) + t for t in TEXT)


def decode(address):
    """Return caption index or neutral; reject stale slot and malformed words."""
    c = Code()
    c.emit("7000")
    c.imm("3039", REPLY_WORD)
    c.emit("2200")
    c.imm("0281", 0xC000)
    c.imm("0c81", 0x8000)
    c.branch(6, "neutral")
    c.emit("2200 e889")
    c.imm("0281", 1023)
    c.emit("7000")
    c.imm("3039", SAMPLE_WORD)
    c.emit("b081")
    c.branch(6, "neutral")
    c.imm("3039", REPLY_WORD)
    c.imm("0280", 15)
    c.imm("0c80", 9)
    c.branch(2, "neutral")
    c.emit("4e75")
    c.label("neutral")
    c.emit("7000 4e75")
    return c.finish(address)


def hint(address, decoder, table, original):
    c = Code()
    c.emit("202f0004")
    c.imm("0c80", 8)
    c.branch(6, "stock")
    c.imm("4eb9", decoder)
    c.emit("d080 d080")
    c.imm("43f9", table)
    c.emit("d3c0 2011 4e75")
    c.label("stock")
    c.imm("4ef9", original)
    return c.finish(address)


def refresh(address, decoder, table):
    """At the native draw seam A2=view; the stock widget argument is on SP.

    Save scratch and A3, compare immutable titles, call the stock setter on
    changes, then tail-call the original widget state getter with its original result.
    No persistent scratch or new allocation ownership is introduced.
    """
    c = Code()
    c.emit("4fefffec 48d70b03")  # D0,D1,A0,A1,A3: 20 bytes
    c.emit("2012")
    c.imm("0c80", 0x401ED888)
    c.branch(6, "done")
    c.emit("206a006c 20680048 2010")
    c.imm("0c80", int.from_bytes(b"CAPI", "big"))
    c.branch(6, "done")
    c.emit("20280004")
    c.imm("0c80", int.from_bytes(b"COLA", "big"))
    c.branch(6, "done")
    c.imm("4eb9", decoder)
    c.emit("d080 d080")
    c.imm("43f9", table)
    c.emit("d3c0 2649 2251 206a006c 20680048 2028fff4")
    c.imm("0c80", 18)
    c.branch(6, "update")
    for offset in (0, 4, 8, 12, 16):
        if offset == 16:
            c.emit("7000 7200")
        c.emit(("3028" if offset == 16 else "2028") + f"{offset:04x}")
        c.emit(("3229" if offset == 16 else "2229") + f"{offset:04x}")
        c.emit("b081")
        c.branch(6, "update")
    c.branch(0, "done")
    c.label("update")
    c.emit("2f0b 2f2a006c")
    c.imm("4eb9", 0x4005B1E0)
    c.emit("508f")
    c.label("done")
    c.emit("4cd70b03 4fef0014")
    c.imm("4ef9", 0x4005B076)
    return c.finish(address)


def patch_cpu(image):
    require(
        hashlib.sha256(image).hexdigest() == BASE_SHA, "Unknown live feedback baseline"
    )
    data, gaps, writes = bytearray(image), [list(g) for g in (*GAPS, *EXTRA_GAPS)], []
    for lo, hi in gaps:
        require(not any(image[lo - BASE : hi - BASE]), "Occupied live feedback padding")

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
        require(
            bool(options), f"Live feedback padding exhausted: {label} ({len(b)} bytes)"
        )
        _, i = min(options)
        a = gaps[i][0]
        put(a, b, label, kind)
        gaps[i][0] = (a + len(b) + 3) & ~3
        return a

    def change(a, before, target, label, jump=False):
        require(
            bytes(data[a - BASE : a - BASE + 6]) == bytes.fromhex(before),
            f"Live feedback byte guard: {label}",
        )
        put(
            a,
            bytes.fromhex("4ef9" if jump else "4eb9") + struct.pack(">I", target),
            label,
            "code",
        )

    updater = allocate(refresh(0, 0, 0), "automatic SRC refresh", "code")
    decoder = allocate(decode(0), "slot status decoder", "code")
    width = allocate(caption_width(0), "Capicola caption width", "code")
    getter = allocate(hint(0, 0, 0, 0), "live status hint", "code")
    title_pointers = [
        allocate(
            struct.pack(">IIi", 18, 18, -1) + t.encode() + b"\0", "title " + repr(t)
        )
        + 12
        for t in TITLES
    ]
    title_table = allocate(struct.pack(">10I", *title_pointers), "title strings")
    pointers = [a + 18 - len(t) for a, t in zip(title_pointers, TEXT, strict=True)]
    hint_table = allocate(struct.pack(">10I", *pointers), "hint strings")
    original = allocate(
        bytes.fromhex("7208202f0004 4ef9") + struct.pack(">I", HINT + 6),
        "original hint trampoline",
        "code",
    )
    put(
        updater,
        refresh(updater, decoder, title_table),
        "linked automatic SRC refresh",
        "code",
    )
    put(decoder, decode(decoder), "linked slot decoder", "code")
    put(
        getter,
        hint(getter, decoder, hint_table, original),
        "linked live status hint",
        "code",
    )
    put(width, caption_width(width), "linked caption width", "code")
    change(HINT, "7208202f0004", getter, "hint dispatch", True)
    change(WIDTH, "721a92832601", width, "caption width")
    change(DRAW, "4eb94005b076", updater, "native draw refresh")
    covered = {
        i
        for w in writes
        for i in range(
            w["address"] - BASE, w["address"] - BASE + len(bytes.fromhex(w["after"]))
        )
    }
    require(
        all(
            x == y or i in covered
            for i, (x, y) in enumerate(zip(image, data, strict=True))
        ),
        "Undeclared live feedback MAIN change",
    )
    result = bytes(data)
    return result, dict(
        sha256=hashlib.sha256(result).hexdigest(),
        writes=writes,
        hint=getter,
        width=width,
        refresh_code=updater,
        decoder=decoder,
        pointers=pointers,
        title_pointers=title_pointers,
        title_table=title_table,
        refresh="native SRC draw path on caption changes",
        wire_version=2,
        reply_word=REPLY_WORD,
        sample_word=SAMPLE_WORD,
        hardware_verified=False,
    )
