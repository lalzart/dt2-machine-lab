"""OS 1.16 sample-pool carve-out for experimental Capicola playback.

Only use on fresh allocator state. Stock preview memory stays above old pool.
This excludes the reservation from inspected allocator paths, not all writers.
"""

import hashlib
import struct

from lab.project import require

BASE = 0x40000400
BASE_SHA = "32081f9ce0db5002e271cdda883feecb54f72c0a1111cb1fa6782f690fe4743a"
# Exact reproduced Plaits R3 + managed streaming Flex + menu image. Keep the
# legacy guard separate so prior experiments cannot silently change baseline.
MANAGED_BASE_SHA = "bc034b810768979db5459b79b05a53ea62c6411bbb07e40c3de337a0129fdef6"
STOCK_BYTES = 0x19000000
RESERVE_BYTES = 8 * 1024 * 1024
SAMPLE_BYTES = STOCK_BYTES - RESERVE_BYTES
RESERVED_BASE = 0x8422B9C8 + SAMPLE_BYTES
BANK_BASE = RESERVED_BASE + 0x100  # Keep test guards inside the reservation.
BANK_END = RESERVED_BASE + RESERVE_BYTES
# Guard full instruction, mutate only its immediate. Preview addresses excluded.
SITES = (
    (0x40153804, "243c", STOCK_BYTES + 0x400, SAMPLE_BYTES + 0x400, "free tail"),
    (0x40153814, "203c", STOCK_BYTES, SAMPLE_BYTES, "free empty"),
    (0x4015381E, "203c", STOCK_BYTES, SAMPLE_BYTES, "total capacity"),
    (0x4015442E, "0c80", STOCK_BYTES + 0x400, SAMPLE_BYTES + 0x400, "tail bound"),
    (0x40154486, "0c82", STOCK_BYTES, SAMPLE_BYTES, "empty feasibility"),
    (0x4015480E, "0c86", STOCK_BYTES, SAMPLE_BYTES, "initial load bound"),
)


def patch_cpu(image, *, managed_flex=False):
    expected = MANAGED_BASE_SHA if managed_flex else BASE_SHA
    require(
        hashlib.sha256(image).hexdigest() == expected,
        "Unknown Capicola reservation baseline",
    )
    data = bytearray(image)
    writes = []
    for address, opcode, before, after, label in SITES:
        old = bytes.fromhex(opcode) + struct.pack(">I", before)
        new = bytes.fromhex(opcode) + struct.pack(">I", after)
        offset = address - BASE
        require(
            data[offset : offset + 6] == old, "Reservation instruction guard: " + label
        )
        data[offset : offset + 6] = new
        writes.append(
            dict(address=address, before=old.hex(), after=new.hex(), label=label)
        )
    return bytes(data), dict(
        writes=writes,
        sample_bytes=SAMPLE_BYTES,
        reserved_bytes=RESERVE_BYTES,
        bank_base=BANK_BASE,
        bank_end=BANK_END,
        baseline_sha256=expected,
        sha256=hashlib.sha256(data).hexdigest(),
        requires_fresh_allocator=True,
        hardware_verified=False,
    )
