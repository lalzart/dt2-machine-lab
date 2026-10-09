"""Guarded OS1.16 Capicola selector/control overlay on the reserved-pool image."""

import hashlib
import struct

from lab.coldfire import audit_code
from lab.project import require

BASE = 0x40000400
BASE_SHA = "7f19553cc4bbdf170378ba67c85bedcf4a57a1d10a4a9751080e249547bd8ff3"
ORDER = (0, 1, 2, 3, 6, 4, 7, 8, 5)
FIELDS = (248, 0, 204, 251, 0, 0, 0, 254, 10)
TABLE = 0x4020F18C


def long(v):
    return struct.pack(">I", v)


def patch_cpu(image):
    import machineprofile

    require(
        hashlib.sha256(image).hexdigest() == BASE_SHA,
        "Unknown Capicola control baseline",
    )
    data = bytearray(image)
    writes = []
    profile = machineprofile.DT2_116

    def read(a, n):
        return image[a - BASE : a - BASE + n]

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

    def change(a, before, after, label, kind="code"):
        require(
            bytes(data[a - BASE : a - BASE + len(before)]) == before
            and len(before) == len(after),
            f"Byte guard: {label}",
        )
        put(a, after, label, kind)

    gaps = [[0x402FDE6C, 0x402FDF66]]
    require(
        not any(read(gaps[0][0], gaps[0][1] - gaps[0][0])),
        "Occupied remaining Flex padding",
    )

    def alloc(b, label, kind="data"):
        choices = [(hi - lo, i) for i, (lo, hi) in enumerate(gaps) if hi - lo >= len(b)]
        require(bool(choices), f"Capicola padding exhausted: {label}")
        _, i = min(choices)
        a = gaps[i][0]
        put(a, b, label, kind)
        gaps[i][0] = (a + len(b) + 3) & ~3
        return a

    # Copy all live table contents before their retired ranges can be reused.
    names = alloc(read(0x403119C4, 96) + bytes(12), "nine display rows")
    ranks = alloc(
        b"".join(struct.pack(">II", t, i) for i, t in enumerate(ORDER)),
        "nine sort ranks",
    )
    listing = alloc(struct.pack(">9I", *ORDER), "nine machine list")
    pertype = alloc(
        read(0x40311984, 8) + read(0x40311984 + 7, 1), "nine per-type bytes"
    )
    gaps.extend(
        [
            [0x403119C4, 0x40311A24],
            [0x40311A84, 0x40311AC4],
            [0x40311944, 0x40311984],
            [0x40311984, 0x4031198C],
        ]
    )
    descriptor = alloc(bytes(44), "Capicola descriptor slot")
    masks = alloc(
        read(0x40311964, 32) + b"\x00\x01" + read(0x40311964 + 7 * 4 + 2, 2),
        "nine permission masks",
    )
    # Special-case only type8, delegate every other input to original Plaits
    # dispatch, preserving signed/invalid fallback behavior.
    dispatch = alloc(
        bytes.fromhex("202f0004 7208 b280 6608 203c")
        + long(descriptor)
        + bytes.fromhex("4e75 4ef9")
        + long(0x403117C4),
        "type8 dispatch",
        "code",
    )

    def rep(s):
        return struct.pack(">IIi", len(s), len(s), -1) + s.encode() + b"\0"

    full = alloc(rep("CAPICOLA"), "Capicola long string") + 12
    short = alloc(rep("CAP"), "Capicola short string") + 12
    rate = alloc(b"Rate\0RATE\0", "Rate labels")
    put(descriptor, struct.pack(">11I", full, short, *FIELDS), "Capicola descriptor")
    put(names + 96, struct.pack(">III", full, short, 0), "Capicola display row")
    # Blank hint shares a pre-existing empty string; no unsupported Slice menu.
    hint = int.from_bytes(read(0x4020EB68 + 5 * 12 + 8, 4), "big")
    put(names + 104, long(hint), "Capicola hint")
    change(
        0x400C8840,
        b"\x4e\xf9" + long(0x403117C4),
        b"\x4e\xf9" + long(dispatch),
        "descriptor dispatch",
    )
    change(
        0x40052A2C,
        bytes.fromhex("4878001c"),
        bytes.fromhex("48780024"),
        "nine-entry list allocation",
    )
    change(
        0x40052A52,
        bytes.fromhex("41e8001c"),
        bytes.fromhex("41e80024"),
        "nine-entry list capacity",
    )
    change(
        0x40052A4C,
        b"\x48\x79" + long(0x40311964),
        b"\x48\x79" + long(listing + 36),
        "list end",
    )
    change(
        0x40052A56,
        b"\x48\x79" + long(0x40311944),
        b"\x48\x79" + long(listing),
        "list start",
    )
    change(
        0x4005E216,
        bytes.fromhex("7207b2806504"),
        bytes.fromhex("7208b2806504"),
        "machine group",
    )
    for fn, col in ((0x400DA548, 0), (0x400DA56E, 4), (0x400DA594, 8)):
        change(fn, bytes.fromhex("7207"), bytes.fromhex("7208"), "name bound")
        site, op = (fn + 16, b"\x41\xf9") if col == 0 else (fn + 18, b"\x06\x80")
        change(site, op + long(0x403119C4 + col), op + long(names + col), "name table")
    change(0x400DA3B2, bytes.fromhex("7407"), bytes.fromhex("7408"), "permission bound")
    change(
        0x400DA3C8,
        b"\x41\xf9" + long(0x40311964),
        b"\x41\xf9" + long(masks),
        "permission table",
    )
    for bound, lea in profile["pertype_sites"]:
        before = read(bound, 2)
        require(before[1] == 7, "Per-type bound drift")
        change(bound, before, before[:1] + b"\x08", "per-type bound")
        before = read(lea, 6)
        require(before[2:] == long(0x40311984), "Per-type pointer drift")
        change(lea, before, before[:2] + long(pertype), "per-type table")
    rank_old = bytes.fromhex(
        "2f08 41f940311a84 2f48000c 41e80040 2f480010 205f 4ef9401aab60"
    )
    rank_new = (
        bytes.fromhex("2f08 41f9")
        + long(ranks)
        + bytes.fromhex("2f48000c 41e80048 2f480010 205f 4ef9401aab60")
    )
    change(0x40311A64, rank_old, rank_new, "nine-rank insert shim")
    change(
        0x400DB2EA,
        bytes.fromhex("7409"),
        bytes.fromhex("740a"),
        "retain type8 on restore",
    )
    # Dormant Sample CFADE is not in any stock or Plaits descriptor. Keep its
    # owner index and all cache-routing fields; only its UI/default changes.
    row = TABLE + 204 * 60
    for off, before, after, label in (
        (16, 0, 16384, "Rate default"),
        (40, int.from_bytes(read(row + 40, 4), "big"), rate, "Rate name"),
        (44, int.from_bytes(read(row + 44, 4), "big"), full, "Rate caption"),
        (48, int.from_bytes(read(row + 48, 4), "big"), rate + 5, "Rate short name"),
    ):
        change(row + off, long(before), long(after), label, "data")
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
        "Undeclared MAIN change",
    )
    return bytes(data), dict(
        status="built",
        order=ORDER,
        fields=FIELDS,
        descriptor=descriptor,
        dispatch=dispatch,
        names=names,
        ranks=ranks,
        listing=listing,
        permissions=masks,
        pertype=pertype,
        writes=writes,
        sha256=hashlib.sha256(data).hexdigest(),
        hardware_ready=False,
    )
