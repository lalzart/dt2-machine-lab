"""Local container checks, not permission or evidence to flash hardware.

Uses the pinned DigiKit writer and an explicitly pinned Elekloader reference
parser/compressor. Elekloader's main-only verifier is deliberately not presented
as validating our two-section change.
"""

import hashlib
import struct

from lab.project import require

REFERENCE_REVISION = "d6449938154a98322a8c0d6844ad10260ab1e065"
FLASH_START = 0x80000
# Conservative ceiling: stock 1.16 accesses its persistent store at 0x380000.
FLASH_LIMIT = 0x380000
DSP_STAGE_BYTES = 0x100000
DSP_COMMAND_BYTES = 1


def verify_dsp_staging(stored_bytes, decoded_bytes):
    """Stock MAIN checks output length only AFTER writing into its allocation.

    The first output byte is boot command3; the depacker starts at buffer+1.
    Reject both independent bounds before any artifact can be handed over.
    """
    require(
        0 < stored_bytes <= DSP_STAGE_BYTES,
        "DSP packed input exceeds stock 1 MiB staging buffer",
    )
    require(
        0 < decoded_bytes <= DSP_STAGE_BYTES - DSP_COMMAND_BYTES,
        "DSP decoded image plus boot command exceeds stock 1 MiB staging buffer",
    )
    return dict(
        input_bytes=stored_bytes,
        decoded_bytes=decoded_bytes,
        command_bytes=DSP_COMMAND_BYTES,
        allocation_bytes=DSP_STAGE_BYTES,
        output_headroom=DSP_STAGE_BYTES - DSP_COMMAND_BYTES - decoded_bytes,
        allocation_sites=["0x400cd174", "0x400cd19e"],
        depacker="0x4013815c",
        post_write_check="0x400cd20c",
    )


def digest(data):
    return hashlib.sha256(data).hexdigest()


def verify_stock_layout(stock):
    """Guard the inspected 1.16 staging and persistent-store address sites."""
    bootstrap = stock.section(2)[4:]
    main = stock.section(3)
    for image, offset, expected in (
        (bootstrap, 0x1C6, "487940400000"),  # stage destination passed to flash read
        (bootstrap, 0x1D4, "068000080000"),  # container flash base added to offset
        (bootstrap, 0x1E6, "4879404000004ebafe44"),  # source passed to depacker
        (main, 0xC9FA0, "2f3c00380000"),  # persistent store header read
        (main, 0xCA116, "2f3c00380000"),  # first store sector operation
        (main, 0xCA12E, "2ebc003c0000"),  # second store sector operation
        (main, 0xCCD74, "2f3c00100000"),  # packed-input allocation
        (main, 0xCCD9E, "2f3c00100000"),  # decoded output allocation
        (main, 0xCCDD4, "0c8000100000"),  # packed-length guard
        (main, 0xCCDF4, "204310fc00032f082f044eb94013815c"),  # command3, output+1
        (main, 0xCCE08, "240052820c8200100000"),  # decoded length+1, after depack
    ):
        wanted = bytes.fromhex(expected)
        require(
            image[offset : offset + len(wanted)] == wanted, "Stock layout guard failed"
        )


def assemble_container(stock, replacements):
    """Replace only stored MAIN/BLOB, preserving all other stored bytes."""
    from dt2 import build
    from dt2.authcode import seal

    require(set(replacements) <= {3, 7}, "Only MAIN and SHARC BLOB may change")
    # 1.16 has a 0x90-byte table area; the pinned generic writer assumes 0x80.
    # Retain the original reserved bytes rather than relocating that boundary.
    body = bytearray(stock.container[: stock.data_start])
    for index, (sid, _, _, dest) in enumerate(stock.table):
        stored = replacements.get(sid, stock.stored[sid])
        struct.pack_into(
            ">IIII", body, 0x20 + 16 * index, sid, len(body), len(stored), dest
        )
        body.extend(stored)
        body.extend(bytes(-len(body) % 16))
    container = seal(bytes(body) + bytes(32), "dt2")
    require(
        FLASH_START + len(container) <= FLASH_LIMIT,
        "Container crosses conservative reserved-flash boundary",
    )
    stream = struct.pack(">II", len(container), build.content_checksum(container))
    return build.encode_syx(stream + container, 0x14, *stock.framing)


def verify_candidate(raw, stock, expected):
    """Reparse and check framing, integrity, destinations and exact content."""
    import hmac

    from dt2 import build
    from dt2.elz import depack_section
    from elekloader import syx
    from elekloader.devices.digitakt_mk2 import DEVICE

    require(set(expected) <= {3, 7}, "Unexpected replacement section")
    verify_stock_layout(stock)
    parsed = syx.Syx(raw)
    require(parsed.device_id == 0x14, "Not a Digitakt II file")
    require(parsed.header == stock.header, "Container identity/version changed")
    require(
        [(s, d) for s, _, _, d in parsed.table]
        == [(s, d) for s, _, _, d in stock.table],
        "Section identity, order or destination changed",
    )
    require(
        FLASH_START + parsed.total <= FLASH_LIMIT,
        "Container crosses conservative reserved-flash boundary",
    )
    canonical = build.encode_syx(
        struct.pack(">II", parsed.total, build.content_checksum(parsed.container))
        + parsed.container,
        0x14,
        *stock.framing,
    )
    require(raw == canonical, "Transport counters/checksums/framing/padding differ")
    key = syx.seal_key(stock, DEVICE)
    require(
        hmac.compare_digest(
            hmac.new(key, parsed.container[:-32], hashlib.sha256).digest(),
            parsed.container[-32:],
        ),
        "HMAC seal mismatch",
    )
    cursor = stock.data_start
    sections = {}
    for sid, offset, length, dest in parsed.table:
        require(offset == cursor, "Noncanonical section layout")
        end = offset + length
        cursor = (end + 15) & ~15
        require(not any(parsed.container[end:cursor]), "Nonzero section padding")
        stored = parsed.stored[sid]
        content = parsed.section(sid)
        if sid == 7:
            dsp_staging = verify_dsp_staging(len(stored), len(content))
        if sid in expected:
            require(syx.classify(stored) == "packed", "Invalid packed section")
            require(content == expected[sid], f"Section {sid} content mismatch")
            require(
                depack_section(stored) == content,
                f"DigiKit/Elekloader decoder disagreement for section {sid}",
            )
        else:
            require(stored == stock.stored[sid], f"Protected section {sid} changed")
            require(content == stock.section(sid), f"Protected section {sid} differs")
        sections[str(sid)] = {
            "destination": hex(dest),
            "stored_bytes": length,
            "stored_sha256": digest(stored),
            "image_bytes": len(content),
            "image_sha256": digest(content),
            "stored_identical_to_stock": stored == stock.stored[sid],
        }
    require(cursor + 32 == parsed.total, "Unexpected container trailer extent")
    require(
        parsed.container[0x20 + 16 * len(parsed.table) : stock.data_start]
        == stock.container[0x20 + 16 * len(stock.table) : stock.data_start],
        "Reserved table bytes changed",
    )
    image, gap = syx.inplace_depack(parsed.stored[3], DEVICE)
    require(image == expected.get(3, stock.section(3)), "Staged MAIN mismatch")
    require(gap > 0, "MAIN decompression overwrites unread input")
    return {
        "sha256": digest(raw),
        "bytes": len(raw),
        "container_bytes": parsed.total,
        "flash_end": hex(FLASH_START + parsed.total),
        "flash_limit": hex(FLASH_LIMIT),
        "flash_limit_basis": "Guarded 1.16 store sites, conservative ceiling; not a complete partition map",
        "main_inplace_min_gap": gap,
        "main_stage_basis": "Guarded 1.16 bootstrap loader at 0x800005c6 and 0x800005e6",
        "sections": sections,
        "dsp_staging": dsp_staging,
        "hardware_ready": False,
    }
