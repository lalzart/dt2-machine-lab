"""Assembler width checks and loader headers without an imported replay run."""

import struct


def assemble(source):
    from sharc_selache import SelacheOracle

    from lab.runtime import SELACHE

    run = SelacheOracle.open(SELACHE).assemble_text(source)
    if not run.comparison.all_extents_agree:
        raise ValueError("Assembler and DigiKit instruction widths disagree")
    return run


def header(target, count, *, fill=None):
    """ADI loader header; a FILL block has no following payload bytes."""
    result = bytearray(
        struct.pack(
            "<IIII",
            0xAD000001 | (0x100 if fill is not None else 0),
            target,
            count,
            0 if fill is None else fill,
        )
    )
    checksum = 0
    for byte in result:
        checksum ^= byte
    result[2] ^= checksum
    return bytes(result)
