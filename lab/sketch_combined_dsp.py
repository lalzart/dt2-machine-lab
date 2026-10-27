"""Add the unchanged author Capicola engine to the exact Sketch DSP image."""

import hashlib

from lab import capicola_layout as layout
from lab import capicola_reddit as capi
from lab.project import require, write_json
from lab.sketch_dsp_device import blocks, check_regions, check_stream, header

COLD_BASE, COLD_END = 0x200B0000, 0x200C0000
BASE_SHA = "37270ca2f528a6dae7d0bd8aa8f463d21e523c1e82217fa12717d849f1f568ae"


def build(base, output):
    import sharcldr

    from lab import runtime  # noqa: F401
    from lab.sharc_tools import assemble

    require(
        hashlib.sha256(base).hexdigest() == BASE_SHA,
        "Combined DSP needs exact Sketchbook base",
    )
    check_stream(base)
    output.mkdir(exist_ok=False)
    hot, cold, symbols = capi.compile_author(
        output / "author", cold_base=COLD_BASE, cold_end=COLD_END
    )
    raw = bytearray(base)
    native_blocks = sharcldr.parse_blocks(raw)
    patches = []
    for site, before, after in (
        (
            0x1C6AF1,
            "CJUMP 0x1c5576 (DB);",
            f"CJUMP {symbols['cc_dt2_entry.']:#x} (DB);",
        ),
        (0x1C75A2, "BIT CLR MODE1 0x200000;", f"JUMP {symbols['lab_capi_frame.']:#x};"),
    ):
        old = assemble(".SECTION/PM seg_pmco;\n" + before + "\n").boot_bytes
        new = assemble(".SECTION/PM seg_pmco;\n" + after + "\n").boot_bytes
        at = sharcldr.offset_for_address(native_blocks, site)
        require(
            len(old) == len(new) and raw[at : at + len(old)] == old,
            "Combined DSP hook conflict",
        )
        raw[at : at + len(new)] = new
        patches.append(dict(site=site, before=old.hex(), after=new.hex()))
    additions = [
        (
            "capi-hot-and-scratch",
            0x28000000 + capi.HOT_BASE,
            hot + bytes(capi.HOT_END - capi.HOT_BASE - len(hot)),
        ),
        ("capi-cold", COLD_BASE, cold + bytes(-len(cold) % 4)),
        ("capi-voices", capi.VOICE_BASE, bytes(capi.VOICE_BYTES)),
        ("capi-rings", capi.RING_BASE, bytes(capi.RING_BYTES)),
        ("capi-status-and-stack", layout.STATE_BASE, bytes(layout.STATE_BYTES)),
    ]

    def physical(at):
        return at - 0x28000000 if 0x28000000 <= at < 0x30000000 else at

    old_memory = sharcldr.LoadedMemory.from_stream(base)
    occupied = [
        (physical(a), physical(a) + b - a)
        for a, b in zip(old_memory._segments[0], old_memory._segments[1], strict=True)
    ]
    for name, at, data in additions:
        start, end = physical(at), physical(at) + len(data)
        require(
            all(end <= lo or start >= hi for lo, hi in occupied),
            "Combined DSP overlap: " + name,
        )
        check_regions([(start, end)])
        occupied.append((start, end))
    items = blocks(raw)
    new_blocks = [
        (1 if any(data) else 0x101, at, len(data), 0, data if any(data) else b"")
        for _, at, data in additions
    ]
    items[-1:-1] = new_blocks
    offsets, offset = [], 0
    for b in items:
        offsets.append(offset)
        offset += 16 + len(b[4])
    firsts = [i for i, b in enumerate(items) if b[0] == 0x5001]
    for index, i in enumerate(firsts):
        next_at = offsets[firsts[index + 1]] if index + 1 < len(firsts) else offset
        b = items[i]
        items[i] = (*b[:3], next_at - offsets[i] - 16, b[4])
    result = b"".join(header(*b[:4]) + b[4] for b in items)
    stream = check_stream(result)
    metadata = dict(
        blob_sha256=hashlib.sha256(result).hexdigest(),
        sketch_base_sha256=BASE_SHA,
        author_source=capi.validate_sources()["sha256"],
        runtime_variant="reddit-release",
        family="sketch+reddit-stretch",
        symbols=symbols,
        patches=patches,
        regions=[
            dict(name=name, start=at, bytes=len(data)) for name, at, data in additions
        ],
        author_hot_bytes=len(hot),
        author_cold_bytes=len(cold),
        cold_base=COLD_BASE,
        cold_end=COLD_END,
        boot_stream=stream,
        algorithms_changed=False,
        plaits=False,
        hardware_verified=False,
    )
    # File aliases let the existing bounded CAPI and recorder probes consume
    # exactly these bytes; neither filename adds a machine to the firmware.
    (output / "SKETCHBOOK_BLOB.bin").write_bytes(result)
    (output / "PLAITS_BLOB.bin").write_bytes(result)
    write_json(output / "build.json", metadata)
    return result, metadata
