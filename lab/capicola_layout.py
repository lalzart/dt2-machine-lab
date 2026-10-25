"""Optional owned working-memory layout; instruction code remains in L2."""

import re

from lab.capicola_memory import BANK_BASE, BANK_END, RESERVED_BASE
from lab.project import require

OLD_BASE = 0x200C0000
OLD_END = 0x200F2000
STATE_BASE = RESERVED_BASE + 0x700000
STATE_BYTES = OLD_END - OLD_BASE
CODE_BASE = 0x20080000
CODE_BYTES = 0x40000
MAX_KEYS = 576004
# Offsets preserve the legacy ABI internally, including independent stacks.
REGIONS = (
    ("constants", 0, 0x10000),
    ("test_stack", 0x16000, 0x18000),
    ("event_stack", 0x18000, 0x1A000),
    ("preparation_stack", 0x1A000, 0x1C000),
    ("voice_stack", 0x1C000, 0x20000),
    ("voice_scratch", 0x20800, 0x20904),
    ("preparation_scratch", 0x20A00, 0x20B00),
    ("event_scratch", 0x20C00, 0x20D00),
    ("plaits_lanes", 0x21000, 0x212C0),
    ("handoff", 0x24000, 0x24024),
    ("bank_descriptor", 0x24100, 0x24120),
    ("capicola_lanes", 0x24200, 0x242A8),
    ("worker", 0x24400, 0x24500),
    ("lifecycle", 0x24500, 0x24528),
    ("preparation_status", 0x24600, 0x2462C),
    ("selector", 0x30000, 0x30024),
)
KERNEL_ADDRESSES = {
    0x200E1000,
    0x200E4000,
    0x200E4008,
    0x200E4010,
    0x200E4014,
    0x200E4018,
    0x200E401C,
    0x200E4100,
    0x200E411C,
    0x200E4200,
    0x200E4400,
    0x200E4418,
    0x200E441C,
    0x200E4424,
    0x200E4500,
    0x200E4504,
    0x200E4508,
    0x200E450C,
    0x200E4510,
    0x200E4514,
    0x200E4518,
}
STRETCH_KERNEL_ADDRESSES = {
    0x200E1000,
    0x200E4000,
    0x200E4008,
    0x200E400C,
    0x200E4020,
    0x200E4100,
    0x200E4104,
    0x200E4108,
    0x200E410C,
    0x200E4110,
    0x200E4114,
    0x200E4118,
    0x200E411C,
    0x200E4400,
    0x200E4418,
    0x200E441C,
    0x200E4424,
    0x200E4500,
    0x200E4504,
    0x200E4508,
    0x200E450C,
    0x200E4510,
    0x200E4514,
    0x200E4518,
    0x200E4600,
    0x200E4800,
    0x200E6000,
}
# Inspected R2 ABI: Plaits, handoff, worker, lifecycle/status, lanes/trace,
# cache header (28 bytes) and its descriptor array. No R1 descriptor aliases.
MULTI_KERNEL_ADDRESSES = {
    0x200E1000,
    0x200E4000,
    0x200E4004,
    0x200E4008,
    0x200E400C,
    0x200E4010,
    0x200E4014,
    0x200E4018,
    0x200E401C,
    0x200E4020,
    0x200E4400,
    0x200E4500,
    0x200E4604,
    0x200E4608,
    0x200E4610,
    0x200E4614,
    0x200E4618,
    0x200E461C,
    0x200E4800,
    0x200E6000,
    0x200E7000,
    0x200E7008,
    0x200E700C,
    0x200E7010,
    0x200E701C,
}
# R3 keeps the inspected R2 cache ABI and moves only lane/trace pointers.
LIVE_KERNEL_ADDRESSES = (MULTI_KERNEL_ADDRESSES - {0x200E4800, 0x200E6000}) | {
    0x200E8000,
    0x200EB000,
}
WRAPPER_ADDRESSES = {0x200DFF00, 0x200DBF00, 0x200D9F00, 0x200E0900}
for _base in (0x200E0800, 0x200E0A00, 0x200E0C00):
    WRAPPER_ADDRESSES.update(range(_base, _base + 256, 4))
TOKENS = re.compile(r"(?<![\w.])(?:0x[0-9a-fA-F]+|[0-9]+)(?![\w.])")


def address(value):
    require(OLD_BASE <= value < OLD_END, "Address outside legacy working region")
    return STATE_BASE + value - OLD_BASE


def validate_layout(layout, integrated, family):
    if family == "capicola-stretch-toggle":
        family = "capicola-stretch-live"
    require(layout in ("legacy", "reserved-state"), "Unknown DSP memory layout")
    if layout == "reserved-state":
        require(
            integrated
            and family
            in (
                "integration",
                "capicola-controls",
                "capicola-selection",
                "capicola-feedback",
                "capicola-live-feedback",
                "capicola-stretch",
                "capicola-stretch-multi",
                "capicola-stretch-live",
            ),
            "Reserved state requires the combined Capicola controls family",
        )


def relocate_assembly(
    source, kind, *, family="capicola-controls", trace=True, cached=False
):
    require(kind in ("kernel", "wrapper"), "Unknown relocation input")
    allowed = KERNEL_ADDRESSES if kind == "kernel" else WRAPPER_ADDRESSES
    if family == "integration":
        allowed = (
            {0x200E1000}
            if kind == "kernel"
            else set(range(0x200E0800, 0x200E0900, 4)) | {0x200E0900, 0x200DFF00}
        )
    if kind == "kernel" and family == "capicola-stretch":
        allowed = STRETCH_KERNEL_ADDRESSES
    if kind == "kernel" and family in (
        "capicola-selection",
        "capicola-feedback",
        "capicola-live-feedback",
    ):
        allowed = KERNEL_ADDRESSES | {0x200E4600}
        if family == "capicola-feedback":
            allowed |= {0x200E4610, 0x200E4618, 0x200E461C}
        elif family == "capicola-live-feedback":
            allowed |= {0x200E460C, 0x200E4610, 0x200E4618, 0x200E461C}
    if kind == "kernel" and family == "capicola-stretch-multi":
        allowed = MULTI_KERNEL_ADDRESSES
    if kind == "kernel" and family == "capicola-stretch-live":
        allowed = LIVE_KERNEL_ADDRESSES
    if kind == "kernel" and family == "capicola-stretch-toggle":
        # Existing AUTO.slices, read by optional track feedback.
        allowed = LIVE_KERNEL_ADDRESSES | {0x200E451C}
    if (
        not trace
        and kind == "kernel"
        and family in ("capicola-stretch-live", "capicola-stretch-toggle")
    ):
        allowed = allowed - {0x200EB000}
    if (
        cached
        and kind == "kernel"
        and family in ("capicola-stretch-live", "capicola-stretch-toggle")
    ):
        # Exclusive end of the 28-byte header + sixteen 88-byte descriptors.
        allowed = allowed | {0x200E7000 + 28 + 16 * 88}
    seen = set()

    def substitute(match):
        value = int(match[0], 0) if match[0].startswith("0x") else int(match[0])
        if not OLD_BASE <= value < OLD_END:
            return match[0]
        require(value in allowed, f"Unreviewed {kind} address {value:#x}")
        seen.add(value)
        return hex(address(value))

    result = TOKENS.sub(substitute, source)
    require(seen == allowed, f"Missing expected {kind} address literals")
    return result


def manifest(code_bytes, data_bytes, *, family="capicola-controls", source=False):
    if family == "capicola-stretch-toggle":
        family = "capicola-stretch-live"
    require(
        0 < code_bytes <= CODE_BYTES and 0 < data_bytes <= 0x10000,
        "Code or constants exceed reserved layout",
    )
    require(BANK_BASE + MAX_KEYS * 12 <= STATE_BASE, "Maximum bank overlaps state")
    require(STATE_BASE + STATE_BYTES <= BANK_END, "State exceeds owned reservation")
    regions = REGIONS
    if family in ("capicola-stretch", "capicola-stretch-multi"):
        regions = (
            REGIONS[:-1]
            + (
                ("stretch_lanes", 0x24800, 0x26000),
                ("stretch_destination_trace", 0x26000, 0x27000),
            )
            + REGIONS[-1:]
        )
    if family == "capicola-stretch-multi":
        regions = regions[:-1] + (("stretch_cache", 0x27000, 0x27800),) + regions[-1:]
    if family == "capicola-stretch-live":
        regions = (
            REGIONS[:-1]
            + (
                ("stretch_cache", 0x27000, 0x28000 if source else 0x27800),
                ("live_lanes", 0x28000, 0x2B000),
                ("live_destination_trace", 0x2B000, 0x2C000),
            )
            + REGIONS[-1:]
        )
    end = 0
    for name, start, limit in regions:
        require(end <= start < limit <= STATE_BYTES, f"Overlapping layout: {name}")
        end = limit
    return {
        "layout": "reserved-state",
        "instruction_code": {
            "start": CODE_BASE,
            "bytes": code_bytes,
            "runtime_ownership_verified": False,
        },
        "state_base": STATE_BASE,
        "state_bytes": STATE_BYTES,
        "bank_maximum_end": BANK_BASE + MAX_KEYS * 12,
        "reservation_end": BANK_END,
        "regions": [
            {"name": n, "start": STATE_BASE + a, "end": STATE_BASE + b}
            for n, a, b in regions
        ],
        "hardware_verified": False,
        **(
            {
                "sample_banks": {
                    "maximum_sources": 32 if source else 16,
                    "arena_start": BANK_BASE,
                    "arena_end": STATE_BASE,
                    "arena_bytes": STATE_BASE - BANK_BASE,
                    "cache_state_bytes": 2844 if source else 1436,
                    "allocation": "measured key count, first fit; no compaction",
                }
            }
            if family in ("capicola-stretch-multi", "capicola-stretch-live")
            else {}
        ),
    }


def check_stock_disjoint(segments):
    for low, high in segments:
        for start, end in (
            (CODE_BASE, CODE_BASE + CODE_BYTES),
            (STATE_BASE, STATE_BASE + STATE_BYTES),
        ):
            require(
                high <= start or low >= end, "Reserved layout overlaps stock loader"
            )
