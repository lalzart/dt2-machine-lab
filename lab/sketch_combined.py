"""Explicit OS1.16 composition of managed Sketch, author CAPI R2 and keyboard ARP.

Existing engines and guards stay authoritative. Shared continuations are named
and byte-checked; arbitrary overlapping patches are never merged.
"""

import copy
import hashlib
import struct

from lab import arp_firmware as arp
from lab import buf_performance as perf
from lab import capicola_memory as memory
from lab import capicola_ui as capi_ui
from lab import recorder_freeze_code as frozen
from lab import recorder_freeze_worker_code as jobs
from lab import sketch_device as sketch
from lab.coldfire import audit_code
from lab.cpu_extension import (
    CAVE,
    GUARD,
    MAIN_LIMIT,
    START,
    STATE,
    Segment,
    loader,
    segment_chain,
)
from lab.cpu_plan import Namespace
from lab.dt2_116 import BASE, STOCK_SHA
from lab.emit import Code
from lab.project import require
from lab.resources import PaddingAllocator, patch_conflicts
from lab.sketch_device_validation import read_segments


def jump(target, size=6):
    require(size >= 6 and size % 2 == 0, "Jump extent")
    return b"\x4e\xf9" + struct.pack(">I", target) + b"\x4e\x71" * ((size - 6) // 2)


def stock_descriptor(address, descriptor, prefix):
    """Specialize STRETCH only, then replay the native seven-machine dispatcher."""
    require(prefix == bytes.fromhex("7206202f0004b280"), "Descriptor prefix drift")
    c = Code()
    c.emit("202f0004")
    c.imm("0c80", 2)
    c.branch(6, "stock")
    c.imm("203c", descriptor)
    c.emit("4e75")
    c.label("stock")
    c.data.extend(prefix)
    c.imm("4ef9", 0x400C8848)
    return c.finish(address)


def build_cpu(stock, image, metadata, output):
    from lab.all_features_base import build_base

    require(hashlib.sha256(stock).hexdigest() == STOCK_SHA, "Combined stock drift")
    require(
        hashlib.sha256(image).hexdigest() == metadata["sha256"], "Sketch image drift"
    )
    require(
        all(
            metadata.get(k)
            for k in (
                "managed_buffers",
                "assign_popup",
                "buf_loading",
                "early_buf_setup",
            )
        ),
        "Combined build requires the current managed startup profile",
    )
    # Reproduce the authenticated source of the CAPI UI. Do not install its
    # Plaits/Flex image. Only named CAPI writes and runtime payloads are reused.
    _, reference = build_base(stock, output / "capi-ui-reference")
    cap = reference["capi_toggle"]
    meta = copy.deepcopy(metadata)
    original_segments = read_segments(image, metadata)
    segments = {s.destination: bytearray(s.data) for s in original_segments}
    image = bytearray(image[: len(stock)])
    allocator = PaddingAllocator(((START + len(GUARD), STATE),))
    plan = arp.plan_cpu(
        stock,
        tempo_ui=True,
        shared_save=False,
        bitmap_mask=True,
        stopped_playback=True,
        any_track=True,
        allocator=Namespace(allocator, "arp"),
    )
    locations = plan.metadata["locations"]
    extra_writes = []
    composed = []

    def main_write(at, before, after, label, kind="code"):
        require(len(before) == len(after), "Main patch extent: " + label)
        off = at - BASE
        require(image[off : off + len(before)] == before, "Main guard: " + label)
        image[off : off + len(after)] = after
        record = dict(
            address=at, before=before.hex(), after=after.hex(), label=label, kind=kind
        )
        previous = next((w for w in meta["hooks"] if w["address"] == at), None)
        if previous is None:
            meta["hooks"].append(record)
        else:
            previous.update(after=after.hex(), label=label)

    def runtime_write(at, before, after, label):
        require(len(before) == len(after), "Runtime patch extent: " + label)
        dest = next(
            (
                d
                for d, raw in segments.items()
                if d <= at and at + len(after) <= d + len(raw)
            ),
            None,
        )
        require(dest is not None, "Unowned continuation: " + label)
        off = at - dest
        require(
            segments[dest][off : off + len(before)] == before,
            "Continuation guard: " + label,
        )
        segments[dest][off : off + len(after)] = after
        owner = next(
            w
            for w in meta["writes"]
            if w["address"] <= at
            and at + len(after) <= w["address"] + len(bytes.fromhex(w["after"]))
        )
        raw = bytearray.fromhex(owner["after"])
        raw[at - owner["address"] : at - owner["address"] + len(after)] = after
        owner["after"] = raw.hex()
        owner["label"] += "+arp"
        # A replaced trampoline is now an ordinary audited absolute jump.
        if at == owner["address"]:
            owner["kind"] = "code"
        audit_code(after, at)
        composed.append(
            dict(address=at, label=label, before=before.hex(), after=after.hex())
        )

    shared = {
        arp.MAINLOOP: (jobs.TRAMP, jobs.GUI_BYTES, "heartbeat"),
        frozen.SAVE: (
            frozen.TRAMPOLINES + 0x700,
            stock[frozen.SAVE - BASE : frozen.SAVE - BASE + 8],
            "save",
        ),
        frozen.LOAD_PROJECT: (
            frozen.TRAMPOLINES + 0x720,
            stock[frozen.LOAD_PROJECT - BASE : frozen.LOAD_PROJECT - BASE + 8],
            "load",
        ),
    }
    for site, (source, prefix, name) in shared.items():
        before = prefix + jump(site + len(prefix))
        runtime_write(
            sketch.relocate(source),
            before,
            jump(locations[name], len(before)),
            "Sketch-to-ARP " + name,
        )
    # Sketch and BUF chords retain first refusal; ARP handles the stock fallback.
    key = next(w for w in meta["writes"] if w["address"] == sketch.relocate(perf.KEY))
    tail = perf.KEY_BYTES + jump(perf.KEY_SITE + len(perf.KEY_BYTES))
    require(bytes.fromhex(key["after"]).endswith(tail), "BUF key fallback drift")
    runtime_write(
        key["address"] + len(bytes.fromhex(key["after"])) - len(tail),
        tail,
        jump(locations["key"], len(tail)),
        "Sketch-to-ARP key",
    )
    for w in plan.writes:
        if w["payload"]:
            extra_writes.append(dict(w))
        elif w["address"] not in (*shared, arp.KEY):
            main_write(
                w["address"],
                bytes.fromhex(w["before"]),
                bytes.fromhex(w["after"]),
                "arp/" + w["label"],
                w["kind"],
            )

    # Native SRAM reset copying supplies the existing small CAPI UI payload.
    # Keep its old addresses, field IDs and strings; replace only its Plaits
    # fallback with a guarded stock-machine dispatcher in the ARP reservation.
    prefix = stock[0x400C8840 - BASE : 0x400C8848 - BASE]
    code = stock_descriptor(0, cap["descriptor"], prefix)
    dispatch = allocator.allocate("capi/stock-descriptor", len(code))
    code = stock_descriptor(dispatch, cap["descriptor"], prefix)
    extra_writes.append(
        dict(
            address=dispatch,
            after=code.hex(),
            kind="code",
            label="capi/stock-descriptor",
            payload=True,
        )
    )
    image.extend(bytes(cap["source_arena_end"] - BASE - len(image)))
    for w in cap["writes"]:
        raw = bytes.fromhex(w["after"])
        if "runtime_address" in w:
            if w["label"] == "STRETCH descriptor dispatch":
                raw = jump(dispatch, len(raw))
            off = w["address"] - BASE
            require(not any(image[off : off + len(raw)]), "CAPI source overlap")
            image[off : off + len(raw)] = raw
            meta["writes"].append(
                dict(
                    address=w["runtime_address"],
                    after=raw.hex(),
                    kind=w["kind"],
                    label="capi/" + w["label"],
                )
            )
        elif w["label"] == "CAPI descriptor lookup":
            main_write(
                w["address"],
                prefix,
                bytes.fromhex(w["after"]) + b"\x4e\x71",
                "capi/descriptor",
            )
        else:
            main_write(
                w["address"],
                bytes.fromhex(w["before"]),
                raw,
                "capi/" + w["label"],
                w["kind"],
            )
    # build_base supplies CAPI's parameter and formatter, but its switch is a
    # separate layer in the all-features builder. Reuse that same stock callback
    # template here so cold boot does not retain the former CFADE knob renderer.
    main_write(
        capi_ui.SITE,
        capi_ui.BEFORE,
        capi_ui.AFTER,
        "capi/stock-binary-switch",
    )
    for at, opcode, old, new, label in memory.SITES:
        main_write(
            at,
            bytes.fromhex(opcode) + struct.pack(">I", old),
            bytes.fromhex(opcode) + struct.pack(">I", new),
            "capi/reservation/" + label,
        )

    require(
        not patch_conflicts([(str(i), [w]) for i, w in enumerate(meta["hooks"])]),
        "Combined MAIN hook overlap",
    )
    require(
        not patch_conflicts([(str(i), [w]) for i, w in enumerate(extra_writes)]),
        "ARP/CAPI payload overlap",
    )
    high = (
        max(
            a + len(bytes.fromhex(w["after"]))
            for w in extra_writes
            for a in [w["address"]]
        )
        + 3
    ) & ~3
    require(high + len(GUARD) <= STATE, "Combined extension overflow")
    arena = bytearray(high - START + len(GUARD))
    arena[: len(GUARD)] = arena[-len(GUARD) :] = GUARD
    for w in extra_writes:
        raw = bytes.fromhex(w["after"])
        arena[w["address"] - START : w["address"] - START + len(raw)] = raw
        meta["writes"].append(w)
    new_segments = [Segment(START, bytes(arena))] + [
        Segment(s.destination, bytes(segments[s.destination]), s.bss)
        for s in original_segments
    ]
    end = metadata["reservation"][1]
    chain = segment_chain(new_segments, reservation=(START, end))
    chain_address = BASE + len(image)
    old_loader = next(w for w in meta["hooks"] if w["address"] == CAVE)
    main_write(
        CAVE,
        bytes.fromhex(old_loader["after"]),
        loader(chain_address),
        "combined/reset-loader",
    )
    image.extend(chain)
    require(len(image) <= MAIN_LIMIT, "Combined MAIN staging ceiling")
    meta.update(
        sha256=hashlib.sha256(image).hexdigest(),
        profile="sketch-capi-r2-arp",
        combined=True,
        sketch_sha256=metadata["sha256"],
        reservation=[START, end],
        reservation_bytes=end - START,
        chain_address=chain_address,
        appended_bytes=len(chain),
        payload_bytes=sum(len(bytes.fromhex(w["after"])) for w in meta["writes"]),
        initialized_bytes=sum(len(s.data) for s in new_segments),
        bss_bytes=sum(s.bss for s in new_segments),
        main_bytes=len(image),
        guards=[[START, len(GUARD)], [high, len(GUARD)], *meta["guards"]],
        segments=[
            dict(
                destination=s.destination,
                data_bytes=len(s.data),
                bss=s.bss,
                sha256=hashlib.sha256(s.data).hexdigest(),
            )
            for s in new_segments
        ],
        arp=plan.metadata,
        capicola=cap,
        continuations=composed,
        capicola_sample_reservation=memory.RESERVE_BYTES,
        limits=[s for s in meta["limits"] if not s.startswith("Isolated profile;")],
    )
    return bytes(image), meta
