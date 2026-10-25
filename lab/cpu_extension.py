"""Opt-in OS1.16 DDR experiment. No runtime code loading or hardware claim.

The reset loader copies appended segments before the stock BSS clear destroys
their stored source. It then calls the original data-copy and clear helpers.
All destinations are validated here; the tiny loader trusts this sealed chain.
"""

import hashlib
import struct
from dataclasses import dataclass

from lab.cpu_plan import Namespace
from lab.dt2_116 import BASE, STOCK_SHA
from lab.project import require
from lab.resources import PaddingAllocator, patch_conflicts

START, LIMIT = 0x47E8B000, 0x47E9B000  # opt-in 64 KiB, not the whole candidate
CANDIDATE_END = 0x47FE0000
CAVE, RESET = 0x403117C4, 0x4000053E
MAIN_LIMIT = 0x3FFC00
RESET_BYTES = bytes.fromhex("4eba ff1c 4eba ff6e")
GUARD = bytes.fromhex("c057a11c5afe1160") * 32
STATE = START + 0xC000


@dataclass(frozen=True)
class Segment:
    destination: int
    data: bytes = b""
    bss: int = 0

    @property
    def end(self):
        return self.destination + len(self.data) + self.bss


def segment_chain(segments, *, reservation=(START, LIMIT)):
    lo_bound, hi_bound = reservation
    require(
        START <= lo_bound < hi_bound <= CANDIDATE_END
        and not (lo_bound | hi_bound) & 3,
        "Invalid extension reservation",
    )
    require(bool(segments), "Empty extension chain")
    result = bytearray()
    previous = []
    for s in segments:
        require(
            isinstance(s.data, bytes) and type(s.bss) is int and s.bss >= 0,
            "Invalid segment contents",
        )
        require(
            len(s.data) + s.bss > 0 and not (s.destination | len(s.data) | s.bss) & 3,
            "Empty or unaligned extension segment",
        )
        require(
            lo_bound <= s.destination < s.end <= hi_bound,
            "Segment exceeds opt-in extension reservation",
        )
        require(
            all(s.end <= lo or s.destination >= hi for lo, hi in previous),
            "Overlapping extension segments",
        )
        previous.append((s.destination, s.end))
        result.extend(struct.pack(">III", len(s.data), s.destination, s.bss))
        result.extend(s.data)
    return bytes(result) + struct.pack(">I", 0xFFFFFFFF)


def loader(chain_address, *, address=CAVE):
    """54-byte ISA_A implementation of the reviewed multi-segment algorithm."""
    require(chain_address % 4 == 0, "Unaligned loader source")
    code = bytearray()
    labels, branches = {}, []

    def emit(h):
        code.extend(bytes.fromhex(h))

    def absolute(h, value):
        emit(h)
        code.extend(struct.pack(">I", value))

    def branch(op, name):
        branches.append((len(code), name))
        code.extend((op, 0))

    absolute("41f9", chain_address)
    labels["next"] = len(code)
    emit("2018 5280")
    branch(0x67, "done")
    emit("5380 2258 2218 e488")
    branch(0x67, "bss")
    labels["copy"] = len(code)
    emit("22d8 5380")
    branch(0x66, "copy")
    labels["bss"] = len(code)
    emit("e489")
    branch(0x67, "next")
    labels["clear"] = len(code)
    emit("4299 5381")
    branch(0x66, "clear")
    branch(0x60, "next")
    labels["done"] = len(code)
    absolute("4eb9", 0x4000045C)
    absolute("4eb9", 0x400004B2)
    emit("4e75")
    for at, name in branches:
        delta = labels[name] - at - 2
        require(-128 <= delta <= 127 and delta != 0, "Loader branch out of range")
        code[at + 1] = delta & 255
    require(len(code) == 54, "Loader encoding changed")
    from lab.coldfire import audit_code

    audit_code(code, address)
    return bytes(code)


def build_cpu(image, *, features="arp-flex", output=None, arp_stopped=False, any_tracks=False,
              flex_save_screen=False):
    """One layout and save owner; optional reviewed Plaits/CAPI CPU base."""
    from lab import arp_firmware, flex_native_build
    from lab.emit import Code
    from lab.project_save import SITE, STOCK_PREFIX, SavePhases, dispatcher

    require(
        hashlib.sha256(image).hexdigest() == STOCK_SHA,
        "CPU extension requires exact stock OS1.16 MAIN",
    )
    require(features in ("arp-flex", "all"), "Unknown extension feature profile")
    require(not any_tracks or features == 'all', 'Any-track requires the all-feature base')
    base_image, base_report, cave = image, None, CAVE
    if features == "all":
        from lab.all_features_base import build_base

        require(output is not None, "All-feature base needs an explicit output")
        base_image, base_report = build_base(image, output)
        cave = base_report["loader_address"]
    allocator = PaddingAllocator(((START + len(GUARD), STATE),))
    arp = arp_firmware.plan_cpu(
        image,
        tempo_ui=True,
        shared_save=True,
        bitmap_mask=True,
        stopped_playback=arp_stopped,
        any_track=any_tracks,
        allocator=Namespace(allocator, "arp"),
    )
    flex = flex_native_build.plan_cpu(
        image,
        managed_sources=True,
        shared_save=True,
        allocator=Namespace(allocator, "flex"),
        save_screen=flex_save_screen,
    )
    a, f = arp.metadata["locations"], flex.metadata["locations"]
    track_payloads = []
    if any_tracks:
        from lab.track_scope import overlay_base, payload

        track_locations, track_payloads = payload(allocator)
        base_image, base_report = overlay_base(image, base_image, base_report, track_locations)
    phases = SavePhases(
        a["save_trampoline"],
        (a["arp_prepare"], f["flex_save_prepare"]),
        (a["arp_commit"],),
        (a["arp_cleanup"],),
    )
    template = dispatcher(0, phases)
    save = allocator.allocate("core/save", len(template))
    # Count actual stock-heartbeat entry into DDR, preserving D0 and incoming SR.
    c = Code()
    c.emit("4feffff0 48d70003 40c0 2f400008")
    c.imm("2039", STATE + 16)
    c.emit("5280")
    c.imm("23c0", STATE + 16)
    c.emit("202f0008 44c0 4cd70003 4fef0010")
    c.imm("4ef9", a["heartbeat"])
    heartbeat = allocator.allocate("core/heartbeat", len(c.finish(0)))
    payloads, hooks = track_payloads[:], []
    for owner, plan in (("arp", arp), ("flex", flex)):
        for w in plan.writes:
            w = dict(w, label=owner + "/" + w["label"])
            if w["payload"]:
                payloads.append(w)
            elif w["address"] != SITE:
                if w["address"] == arp_firmware.MAINLOOP:
                    w["after"] = (b"\x4e\xf9" + struct.pack(">I", heartbeat)).hex()
                hooks.append(w)
    # The only shared stock write is replaced by this phased dispatcher.
    hooks.append(
        dict(
            address=SITE,
            before=STOCK_PREFIX.hex(),
            after=(b"\x4e\xf9" + struct.pack(">I", save) + b"\x4e\x71").hex(),
            label="core/project-save",
            kind="code",
            payload=False,
        )
    )
    for address, data, label in (
        (save, dispatcher(save, phases), "core/save"),
        (heartbeat, c.finish(heartbeat), "core/heartbeat"),
    ):
        payloads.append(
            dict(
                address=address,
                before=bytes(len(data)).hex(),
                after=data.hex(),
                label=label,
                kind="code",
                payload=True,
            )
        )
    base_writes = base_report["writes"] if base_report else []
    require(
        not patch_conflicts(
            [(str(i), [w]) for i, w in enumerate(hooks + payloads + base_writes)]
        ),
        "Composed CPU writes overlap",
    )
    high = (max(hi for _, hi in allocator.allocations.values()) + 3) & ~3
    require(high + len(GUARD) <= STATE, "Extension payload exhausted")
    run = bytearray(high - START + len(GUARD))
    run[: len(GUARD)] = GUARD
    run[-len(GUARD) :] = GUARD
    for w in payloads:
        code = bytes.fromhex(w["after"])
        off = w["address"] - START
        run[off : off + len(code)] = code
    segments = (
        Segment(START, bytes(run)),
        Segment(STATE, b"CPUX" + struct.pack(">III", 1, START, LIMIT), 4096),
        Segment(LIMIT - len(GUARD), GUARD),
    )
    chain = segment_chain(segments)
    data = bytearray(base_image)
    for w in hooks:
        off = w["address"] - BASE
        before, after = bytes.fromhex(w["before"]), bytes.fromhex(w["after"])
        require(
            data[off : off + len(before)] == before,
            "Composition byte guard " + w["label"],
        )
        data[off : off + len(after)] = after
    chain_address = BASE + len(base_image)
    code = loader(chain_address, address=cave)
    for address, before, after, label in (
        (cave, bytes(len(code)), code, "core/reset-loader"),
        (
            RESET,
            RESET_BYTES,
            b"\x4e\xb9" + struct.pack(">I", cave) + b"\x4e\x71",
            "core/reset-hook",
        ),
    ):
        off = address - BASE
        require(data[off : off + len(before)] == before, "Reset byte guard " + label)
        data[off : off + len(after)] = after
        hooks.append(
            dict(
                address=address,
                before=before.hex(),
                after=after.hex(),
                label=label,
                kind="code",
                payload=False,
            )
        )
    require(
        data[0x40312000 - BASE :] == base_image[0x40312000 - BASE :],
        "Reset-copy data changed",
    )
    data.extend(chain)
    require(len(data) <= MAIN_LIMIT, "Expanded MAIN exceeds staging ceiling")
    metadata = dict(
        firmware="Digitakt II OS1.16",
        experimental=True,
        hardware_ready=False,
        stock_sha256=STOCK_SHA,
        sha256=hashlib.sha256(data).hexdigest(),
        reservation=[START, LIMIT],
        reservation_bytes=LIMIT - START,
        payload_bytes=sum(len(bytes.fromhex(w["after"])) for w in payloads),
        initialized_bytes=sum(len(s.data) for s in segments),
        bss_bytes=sum(s.bss for s in segments),
        appended_bytes=len(chain),
        main_bytes=len(data),
        loader_bytes=len(code),
        loader_address=cave,
        chain_address=chain_address,
        features=features,
        base=base_report,
        allocations=allocator.allocations,
        arp=arp.metadata,
        flex=flex.metadata,
        heartbeat_counter=STATE + 16,
        save_dispatcher=save,
        save_phases=dict(
            stock=phases.stock,
            prepare=phases.prepare,
            commit=phases.commit,
            cleanup=phases.cleanup,
        ),
        writes=base_writes + hooks + payloads,
        guards=[
            [START, len(GUARD)],
            [high, len(GUARD)],
            [LIMIT - len(GUARD), len(GUARD)],
        ],
        segments=[
            dict(
                destination=s.destination,
                data_bytes=len(s.data),
                bss=s.bss,
                sha256=hashlib.sha256(s.data).hexdigest(),
            )
            for s in segments
        ],
    )
    if any_tracks:
        metadata.update(any_tracks=True, track_locations=track_locations)
    if flex_save_screen:
        metadata["flex_save_screen"] = True
        metadata["flex_bank_choice"] = True
    return bytes(data), metadata
