"""Guarded display-order overlay for the existing OS 1.16 Plaits R3 build."""

import hashlib
import struct

from lab.project import require

BASE = 0x40000400
LIST = 0x40311944
RANK = 0x40311A84
OLD_ORDER = (0, 1, 2, 3, 6, 4, 5, 7)
ORDER = (0, 1, 2, 3, 6, 4, 7, 5)
# The exact combined R3 + native Flex twenty-second image, before this overlay.
BASE_SHA = "24b6f9fcdde519299a67738d7d4cb166d90f0e53e15e5dd55e88a7e90fee0363"
MANAGED_BASE_SHA = "95d0204a362f7758d3ba2a84925d55c314c024ed20bca4ca34dd5b2c25c0d6be"


def patch_cpu(image):
    require(
        hashlib.sha256(image).hexdigest() in (BASE_SHA, MANAGED_BASE_SHA),
        "Unknown menu baseline",
    )
    data = bytearray(image)
    writes = []
    for address, before, after, label in (
        (
            LIST,
            struct.pack(">8I", *OLD_ORDER),
            struct.pack(">8I", *ORDER),
            "machine list",
        ),
        (
            RANK,
            b"".join(struct.pack(">II", typ, i) for i, typ in enumerate(OLD_ORDER)),
            b"".join(struct.pack(">II", typ, i) for i, typ in enumerate(ORDER)),
            "machine sort ranks",
        ),
    ):
        off = address - BASE
        require(data[off : off + len(before)] == before, f"Menu byte guard: {label}")
        data[off : off + len(after)] = after
        writes.append(
            dict(
                address=address,
                before=before.hex(),
                after=after.hex(),
                label=label,
                kind="data",
            )
        )
    return bytes(data), dict(
        order=list(ORDER), machine_ids_unchanged=True, writes=writes
    )
