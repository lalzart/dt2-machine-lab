"""Device-only DSP placement, preserving the prepared-emulator default layout.

ADI reserves L2's last 8 KiB for the boot kernel until boot finishes. A loader
FILL block writes that area just as a literal block does. This guard concerns
bootability; it does not certify stock dynamic ownership, caches or hardware.
"""

import struct
from functools import reduce
from operator import xor

from lab.project import require, sha256, write_json

BOOT_WORKSPACE = (0x200FE000, 0x20100000)
GATE_STATE, GATE_END = 0x200E8000, 0x200EC000
SOURCE = (
    "https://ez.analog.com/dsp/sharc-processors/adsp-2156x/f/q-a/"
    "566931/secure-booting---using-secure-boot_open-part-directory"
)
ROM_SOURCE = (
    "https://www.analog.com/media/en/dsp-documentation/processor-manuals/"
    "adsp-2156x_hwr.pdf"
)


def blocks(blob):
    """Read every byte, including legacy appends after FINAL; never stop silently.

    This is only the OS1.16 subset: BCODE 1, literal/FILL, FIRST|IGNORE, INIT,
    FINAL. Unsupported flags fail closed instead of modelling callbacks.
    """
    at, result = 0, []
    while at < len(blob):
        require(at + 16 <= len(blob), "Truncated DSP boot header")
        raw = blob[at : at + 16]
        code, target, count, argument = struct.unpack("<4I", raw)
        require(code >> 24 == 0xAD, "Invalid DSP boot signature")
        require(reduce(xor, raw) == 0, "Invalid DSP boot checksum")
        flags = code & 0xFFFF
        require(
            flags in (1, 0x101, 0x5001, 0x801, 0x8001), "Unsupported DSP boot flags"
        )
        end = at + 16 + (0 if flags & 0x100 else count)
        require(end <= len(blob), "Truncated DSP boot payload")
        result.append((flags, target, count, argument, blob[at + 16 : end]))
        at = end
    return result


def header(flags, target, count, argument):
    raw = bytearray(struct.pack("<4I", 0xAD000000 | flags, target, count, argument))
    raw[2] = reduce(xor, raw)
    return bytes(raw)


def check_stream(blob):
    """Documented boot rules plus stock FIRST next-application convention.

    HWR chapter 40, pp.40-39..43, 40-85. This validates a stream; it does not
    execute the ROM or qualify the physical SPI tail/ready-line behaviour.
    """
    items = blocks(blob)
    require(0 < len(blob) <= 0xFFFFF, "DSP boot stream exceeds sender capacity")
    require(items[0][0] == 0x5001, "DSP boot stream lacks initial FIRST")
    require(items[-1][0] == 0x8001, "DSP boot stream lacks terminal FINAL")
    require(all(b[0] != 0x8001 for b in items[:-1]), "DSP boot bytes after FINAL")
    firsts, at = [], 0
    for flags, target, count, argument, payload in items:
        require(count % 4 == 0, "Unaligned DSP boot byte count")
        if flags == 0x801:
            require(target % 4 == 0, "Unaligned DSP INIT target")
        if count and flags != 0x5001:
            require(target % 4 == 0, "Unaligned DSP boot load target")
            check_regions([(target, target + count)])
        if flags == 0x5001:
            firsts.append((at, argument))
        at += 16 + len(payload)
    for i, (at, argument) in enumerate(firsts):
        next_at = firsts[i + 1][0] if i + 1 < len(firsts) else len(blob)
        require(
            argument == next_at - at - 16, "Stale DSP FIRST next-application pointer"
        )
    return dict(
        blocks=len(items),
        bytes=len(blob),
        command_and_stream_tail_mod_1024=(len(blob) + 1) % 1024,
        final_is_last=True,
        headers_alignment_workspace_and_first_pointers_checked=True,
        rom_executed=False,
        source=ROM_SOURCE,
    )


def finish_stream(blob, stock):
    """Device serialization only; retain the legacy prepared-emulator recipe.

    Authenticate every original header, insert the six added blocks before
    FINAL, pad literal tails to 32-bit DMA alignment, then repair FIRST spans.
    No existing loaded payload byte or target address is changed.
    """
    check_stream(stock)
    original, items = blocks(stock), blocks(blob)
    require(len(items) == len(original) + 6, "Unexpected device DSP block count")
    require(
        [b[:4] for b in items[: len(original)]] == [b[:4] for b in original],
        "Stock DSP boot headers changed",
    )
    extras = items[len(original) :]
    require(
        [(b[0], b[1]) for b in extras]
        == [
            (1, 0x20080000),
            (0x101, 0x200F4000),
            (1, 0x200D0000),
            (0x101, GATE_STATE),
            (1, 0x200C0000),
            (0x101, 0x200F8000),
        ],
        "Unknown device DSP additions",
    )
    padded = []
    for flags, target, count, argument, payload in extras:
        if flags == 1:
            pad = (-count) % 4
            payload += bytes(pad)  # Unexecuted bytes after the emitted code.
            count += pad
        padded.append((flags, target, count, argument, payload))
    items = items[: len(original) - 1] + padded + [original[-1]]
    offsets, at = [], 0
    for b in items:
        offsets.append(at)
        at += 16 + len(b[4])
    firsts = [i for i, b in enumerate(items) if b[0] == 0x5001]
    for n, i in enumerate(firsts):
        b = items[i]
        end = offsets[firsts[n + 1]] if n + 1 < len(firsts) else at
        items[i] = (*b[:3], end - offsets[i] - 16, b[4])
    result = b"".join(header(*b[:4]) + b[4] for b in items)
    check_stream(result)
    return result


def check_regions(regions):
    """Check decoded destination extents, including zero-fill destinations."""
    for lo, hi in regions:
        require(0 <= lo < hi <= 0x100000000, "Invalid DSP memory extent")
        require(
            hi <= BOOT_WORKSPACE[0] or lo >= BOOT_WORKSPACE[1],
            f"DSP boot workspace overlap: {lo:#x}..{hi:#x}",
        )


def audit(blob):
    from lab import runtime  # isort: skip; initialize pinned loader import path
    import sharcldr

    require(
        sha256(runtime.STOCK_BLOB)
        == "0f514a12a2255f5c081e292c47f1f29462003177658da4bbae0a22fd737fffa2",
        "Unknown stock DSP",
    )
    stream = check_stream(blob)
    require(
        blob[:0x2974] == runtime.STOCK_BLOB.read_bytes()[:0x2974],
        "Stock DSP init application changed",
    )
    memory = sharcldr.LoadedMemory.from_stream(blob)
    require(
        sharcldr.entry_points(memory.blocks) == [0x120230, 0x1C1338],
        "Unknown OS1.16 DSP entries",
    )
    regions = list(zip(memory._segments[0], memory._segments[1], strict=True))
    check_regions(regions)
    require(
        memory.read(GATE_STATE, GATE_END - GATE_STATE) == bytes(GATE_END - GATE_STATE),
        "Device gate state not initialized at its reserved address",
    )
    return dict(
        gate_state=[GATE_STATE, GATE_END],
        excluded_boot_workspace=list(BOOT_WORKSPACE),
        loaded_regions=[list(region) for region in regions],
        boot_workspace_untouched=True,
        physical_ownership_qualified=False,
        boot_stream=stream,
        init_application_stock_exact=True,
        source=SOURCE,
    )


def build(output):
    from lab import runtime
    from lab.recorder_native_retirement import build as native_build

    blob, metadata = native_build(output, gate_state=GATE_STATE)
    legacy_hash = metadata["blob_sha256"]
    blob = finish_stream(blob, runtime.STOCK_BLOB.read_bytes())
    (output / "RETIRE_BLOB.bin").write_bytes(blob)
    metadata = dict(
        metadata,
        blob_sha256=sha256(output / "RETIRE_BLOB.bin"),
        legacy_stream_sha256=legacy_hash,
        device_placement=audit(blob),
    )
    write_json(output / "build.json", metadata)
    return blob, metadata
