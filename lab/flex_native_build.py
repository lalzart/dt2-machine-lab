"""Version-guarded native Flex MAIN overlay, composable with the Plaits R3 CPU.

This builds an experimental image for validation, not a hardware-ready package.
Candidate padding requires boot/UI checks in addition to the static guards.
"""

import hashlib
import struct

from lab import flex_native as native
from lab import flex_native_save as named
from lab.coldfire import audit_code
from lab.project import require

BASE = 0x40000400
STOCK_SHA = "57bb4dfa8df07d846adc72fdb4fb0d3cd3c5680c524bf498338460207e008e7d"
R3_SHA = "6f5a9df5f1bf17c002c7755e1682051aff9e2d990238ec62722c5a459e8e9543"
# Exact zero intervals from the pinned 1.16 deep-reference scan. Deliberately
# exclude Plaits' entire 0x403117c4..0x40312000 allocation and reset-copy data.
# These are candidate locations until the dynamic placement checks pass.
CANDIDATE_GAPS = (
    (0x402E4A24, 0x402E4DA4),
    (0x402E5B5C, 0x402E5EDC),
    (0x402FE45C, 0x402FE5DC),
    (0x402FDE60, 0x402FDF66),
    (0x402FDA60, 0x402FDB5E),
    (0x402FD660, 0x402FD75E),
    (0x40300AE0, 0x40300BDE),
    (0x402FD45C, 0x402FD556),
    (0x402FD85C, 0x402FD956),
    (0x402FDC5C, 0x402FDD56),
    (0x402FE05C, 0x402FE156),
    (0x403010DC, 0x403011D6),
    (0x403014DC, 0x403015D6),
    (0x402FCE64, 0x402FCF5E),
    (0x402FD05C, 0x402FD156),
    (0x402FD264, 0x402FD35E),
    (0x403016E4, 0x403017DE),
    (0x403018DC, 0x403019D6),
)
# Additional candidates from the same exact OS 1.16 caves-small.json scan.
# Optional ownership experiment only; boot/asset-path validation is separate.
OWNERSHIP_GAPS = (
    (0x402FCC5C, 0x402FCD34),
    (0x40301CDC, 0x40301DB4),
    (0x402FCA98, 0x402FCB5C),
    (0x40301B18, 0x40301BDC),
    (0x402FC718, 0x402FC75C),
    (0x403020DC, 0x40302134),
    (0x402FC85C, 0x402FC8A8),
    (0x40301F98, 0x40301FDC),
)


def build_payload(
    locations,
    *,
    compact_resources=False,
    separate_source=False,
    memory_accounting=False,
    durable_reads=False,
    managed_sources=False,
):
    if managed_sources:
        compact_resources = separate_source = durable_reads = True
        memory_accounting = True
    p = locations

    def at(key):
        return p.get(key, 0)

    errors = {name: index for index, name in enumerate(native.USE_ERRORS)}
    payload = {
        "state": (bytes(56), "data"),
        "path_format": (b"/recorded/FLEX-%08X-%02u\0", "data"),
        "directory": (b"/recorded\0", "data"),
        **{
            "error_" + name: (text.encode("ascii") + b"\0", "data")
            for name, text in native.USE_ERRORS.items()
        },
        "error_table": (
            b"".join(
                struct.pack(">I", at("error_" + name)) for name in native.USE_ERRORS
            ),
            "data",
        ),
        "error_text": (
            native.recorder_error_text(
                at("error_text"), at("state"), at("error_table")
            ),
            "code",
        ),
        "copy": (native.recording_copy(at("copy")), "code"),
        "lookup": (native.resource_lookup(at("lookup"), at("state")), "code"),
        "accept": (
            native.accept_recording(
                at("accept"),
                at("copy"),
                errors,
                separate_source=separate_source,
                discard=(at("discard_candidate") or 1) if managed_sources else 0,
            ),
            "code",
        ),
        "assign": (native.assign_recording(at("assign")), "code"),
    }
    save, after_open = native.save_recording(
        at("save_raw") if managed_sources else at("save"),
        backing_reader=(at("read_backing") or 1) if managed_sources else 0,
    )
    payload["save_raw" if managed_sources else "save"] = (save, "code")
    if managed_sources:
        from lab import flex_retirement as owner
        from lab.flex_resources import split_native

        payload["pin_source"] = (owner.pin_source(at("pin_source")), "code")
        payload["abort_source"] = (owner.abort_source(at("abort_source")), "code")
        payload["discard_candidate"] = (
            owner.discard_candidate(at("discard_candidate"), at("abort_source")),
            "code",
        )
        payload["unpin_source"] = (
            owner.unpin_source(at("unpin_source"), abort=at("abort_source") or 1),
            "code",
        )
        keys = ("retire_source", "retire_source_1")
        for key, part in zip(
            keys,
            split_native(owner.retire_source(0), [at(k) for k in keys]),
            strict=True,
        ):
            payload[key] = (part, "code")
        payload["save"] = (
            owner.save_owned(
                at("save"),
                at("pin_source"),
                at("unpin_source"),
                at("read_backing"),
                at("save_raw"),
            ),
            "code",
        )
    payload["exclusive_open"] = (
        native.exclusive_open_guard(at("exclusive_open"), after_open),
        "code",
    )
    payload["persist"] = (
        native.persist_project_pool(
            at("persist"),
            at("lookup"),
            at("save"),
            at("path_format"),
            at("directory"),
            retire=(at("retire_source") or 1) if managed_sources else 0,
        ),
        "code",
    )
    payload["project_save"] = (
        native.project_save_guard(at("project_save"), at("persist")),
        "code",
    )
    payload["use_entry"] = (
        native.recorder_use_entry(at("use_entry"), at("state")),
        "code",
    )
    payload["use_worker"] = (
        native.recorder_use_worker(
            at("use_worker"), at("state"), at("accept"), errors, managed=managed_sources
        ),
        "code",
    )
    payload["error_trampoline"] = (
        bytes.fromhex("4e56ffa4206e0008 4ef940021974"),
        "stock-trampoline",
    )
    payload["use_finish"] = (
        native.recorder_use_finish(
            at("use_finish"),
            at("state"),
            at("assign"),
            at("error_trampoline"),
            errors,
            discard=(at("discard_candidate") or 1) if managed_sources else 0,
        ),
        "code",
    )
    for key, text in {
        "save_title": "SAVE FLEX SAMPLE",
        "save_initial": "FLEX",
        "save_success": "FLEX SAVED" if managed_sources else "FLEX: SAMPLE SAVED",
        "save_failure": "FLEX: SAVE FAILED",
        "save_missing": "FLEX: NO FLEX SAMPLE",
        "save_use_first": "FLEX: USE TAKE FIRST",
    }.items():
        payload[key] = (text.encode("ascii") + b"\0", "data")
    payload["save_pool"] = (named.current_pool(at("save_pool")), "code")
    payload["save_target"] = (
        named.target(at("save_target"), at("save_pool"), at("lookup")),
        "code",
    )
    payload["dialog_push"] = (named.push_dialog(at("dialog_push")), "code")
    payload["save_message"] = (
        named.message(at("save_message"), at("dialog_push")),
        "code",
    )
    payload["save_manager"] = (named.manager(at("save_manager")), "code")
    payload["save_open"] = (
        named.open_name(
            at("save_open"),
            at("save_manager"),
            at("save_callback"),
            at("dialog_push"),
            at("save_title"),
            at("save_initial"),
        ),
        "code",
    )
    payload["save_promote"] = (
        named.promote(
            at("save_promote"),
            retire=(at("retire_source") or 1) if managed_sources else 0,
        ),
        "code",
    )
    payload["save_named"] = (
        named.write_named(
            at("save_named"),
            at("save_pool"),
            at("save"),
            at("save_promote"),
            at("directory"),
        ),
        "code",
    )
    payload["save_callback"] = (
        named.named_callback(
            at("save_callback"),
            at("save_named"),
            at("save_message"),
            at("save_success"),
            at("save_failure"),
            success_callback=(at("memory_saved_message") or 1)
            if managed_sources
            else 0,
        ),
        "code",
    )
    payload["recorder_keys_trampoline"] = (
        bytes.fromhex("4e56ff6c48d73cfc4ef940022c76"),
        "stock-trampoline",
    )
    payload["recorder_keys"] = (
        named.recorder_keys(
            at("recorder_keys"),
            at("save_target"),
            at("save_open"),
            at("save_message"),
            at("save_missing"),
            at("save_use_first"),
            at("recorder_keys_trampoline"),
        ),
        "code",
    )
    for operation, (entry, before_hex) in native.RESOURCE_SITES.items():
        before = bytes.fromhex(before_hex)
        key = operation + "_trampoline"
        payload[key] = (
            before + b"\x4e\xf9" + struct.pack(">I", entry + len(before)),
            "stock-trampoline",
        )
        payload[operation] = (
            native.resource_handler(at(operation), at("lookup"), operation, at(key)),
            "code",
        )
    if compact_resources:
        from lab import flex_resources as shared

        if durable_reads:
            from lab.flex_retirement import read_backing

            payload["read_backing"] = (read_backing(at("read_backing")), "code")

        payload["resource_fallbacks"] = (
            b"".join(
                struct.pack(">I", at(op + "_trampoline")) for op in shared.OPERATIONS
            ),
            "data",
        )
        resource_keys = ["resource_dispatch", "resource_dispatch_1"]
        if durable_reads:
            resource_keys.append("resource_dispatch_2")
        for i, part in enumerate(
            shared.parts(
                [at(key) for key in resource_keys],
                at("lookup"),
                at("resource_fallbacks"),
                durable_reader=(at("read_backing") or 1) if durable_reads else 0,
                source_pin=(at("pin_source") or 1) if managed_sources else 0,
                source_unpin=(at("unpin_source") or 1) if managed_sources else 0,
            )
        ):
            payload[resource_keys[i]] = (
                part,
                "code",
            )
        for operation in shared.OPERATIONS:
            payload[operation] = (
                shared.entry(at(operation), operation, at("resource_dispatch")),
                "code",
            )
        if separate_source:
            original = native.accept_recording(
                0,
                at("copy"),
                errors,
                separate_source=True,
                discard=(at("discard_candidate") or 1) if managed_sources else 0,
            )
            keys = ("accept", "accept_1", "accept_2")
            for key, part in zip(
                keys, shared.split_native(original, [at(k) for k in keys]), strict=True
            ):
                payload[key] = (part, "code")
    if memory_accounting:
        from lab.flex_memory import snapshot

        payload["memory_snapshot"] = (
            snapshot(at("memory_snapshot"), separate_source=separate_source),
            "code",
        )
    if managed_sources:
        from lab.flex_memory import saved_message

        payload["memory_saved_format"] = (
            b"FLEX SAVED\nRAM %u B\nTAKES %u/32\0",
            "data",
        )
        payload["memory_saved_buffer"] = (bytes(64), "data")
        payload["memory_saved_message"] = (
            saved_message(
                at("memory_saved_message"),
                at("state"),
                at("memory_snapshot"),
                at("memory_saved_format"),
                at("memory_saved_buffer"),
                at("save_message"),
                at("save_success"),
            ),
            "code",
        )
    return payload


def patch_cpu(
    image,
    *,
    compact_resources=False,
    separate_source=False,
    memory_accounting=False,
    durable_reads=False,
    managed_sources=False,
):
    if managed_sources:
        compact_resources = separate_source = durable_reads = True
        memory_accounting = True
    require(
        not durable_reads or compact_resources,
        "Durable reads require compact resources",
    )
    baseline = hashlib.sha256(image).hexdigest()
    require(
        baseline in (STOCK_SHA, R3_SHA),
        "Native Flex requires exact stock 1.16 or audited Plaits R3",
    )
    data, writes = bytearray(image), []
    gaps = [
        list(g) for g in CANDIDATE_GAPS + (OWNERSHIP_GAPS if managed_sources else ())
    ]
    for lo, hi in gaps:
        require(BASE <= lo < hi <= 0x403117C4, "Invalid native Flex placement")
        require(
            not any(data[lo - BASE : hi - BASE]),
            f"Occupied native Flex padding {lo:#x}",
        )
    locations = {}
    options = dict(
        compact_resources=compact_resources,
        separate_source=separate_source,
        memory_accounting=memory_accounting,
        durable_reads=durable_reads,
        managed_sources=managed_sources,
    )
    template = build_payload({}, **options)
    sizes = {key: len(value[0]) for key, value in template.items()}
    for key, length in sorted(
        sizes.items(),
        key=lambda item: (
            -(
                sizes["retire_source"]
                if managed_sources and item[0] == "retire_source_1"
                else item[1]
            ),
            item[0],
        ),
    ):
        # ColdFire code needs word alignment (stock entries include 0x4011e87a).
        # Keep long data aligned; legacy placement continues to use four bytes.
        alignment = 2 if managed_sources and template[key][1] != "data" else 4
        starts = [((lo + alignment - 1) // alignment) * alignment for lo, _ in gaps]
        choices = [
            (hi - starts[i], i)
            for i, (_, hi) in enumerate(gaps)
            if hi - starts[i] >= length
        ]
        # Split routines retain word branches; keep their parts in range.
        if managed_sources:
            for family in ("accept", "resource_dispatch", "retire_source"):
                if key == family or key.startswith(family + "_"):
                    peers = [
                        value
                        for name, value in locations.items()
                        if name == family or name.startswith(family + "_")
                    ]
                    choices = [
                        (room, i)
                        for room, i in choices
                        if all(abs(starts[i] - peer) < 32000 for peer in peers)
                    ]
        require(choices, f"Native Flex padding exhausted: {key}")
        _, index = min(choices)
        locations[key] = starts[index]
        gaps[index][0] = (
            starts[index] + ((length + alignment - 1) // alignment) * alignment
        )

    def put(address, before, after, label, kind):
        off = address - BASE
        require(
            len(before) == len(after) and data[off : off + len(before)] == before,
            f"Native Flex byte guard: {label} {address:#x}",
        )
        decoded = audit_code(after, address) if kind == "code" else []
        if kind == "stock-trampoline":
            require(after[-6:-4] == b"\x4e\xf9", "Invalid stock trampoline tail")
            # Prefixes are exact, separately guarded, PC-independent stock
            # prologues. Audit the newly emitted absolute jump independently.
            audit_code(after[-6:], address + len(after) - 6)
        data[off : off + len(after)] = after
        writes.append(
            dict(
                address=address,
                before=before.hex(),
                after=after.hex(),
                label=label,
                kind=kind,
                instructions=decoded,
            )
        )

    for key, (code, kind) in build_payload(locations, **options).items():
        require(len(code) == sizes[key], "Native relocation changed payload size")
        put(locations[key], bytes(len(code)), code, key, kind)

    def hook(entry, before_hex, destination):
        before = bytes.fromhex(before_hex)
        code = b"\x4e\xf9" + struct.pack(">I", locations[destination])
        code += b"\x4e\x71" * ((len(before) - 6) // 2)
        put(entry, before, code, destination + " hook", "code")

    for operation, (entry, before_hex) in native.RESOURCE_SITES.items():
        hook(entry, before_hex, operation)
    hook(0x401586B8, "66544a826724", "exclusive_open")
    hook(0x40043A30, "4fefffcc48d77c1c", "project_save")
    hook(0x40022FBE, "4879402297197e01", "use_entry")
    hook(0x4001FC48, "4fefffd848d73c3c", "use_worker")
    hook(0x4002196C, "4e56ffa4206e0008", "use_finish")
    hook(0x40022C6E, "4e56ff6c48d73cfc", "recorder_keys")
    put(
        0x40021986,
        bytes.fromhex("487940229675"),
        b"\x4e\xf9" + struct.pack(">I", locations["error_text"]),
        "Flex error text reference",
        "code",
    )
    put(0x402296FB, b"Y:SAVE\0", b"Y:USE \0", "recorder action label", "data")
    return bytes(data), dict(
        baseline_sha256=baseline,
        sha256=hashlib.sha256(data).hexdigest(),
        firmware="Digitakt II OS 1.16",
        locations=locations,
        ownership_options=options,
        writes=writes,
        payload_bytes=sum(sizes.values()),
        status="experimental-native-image",
        hardware_ready=False,
        scope="Native device instructions; boot, UI scheduling, full project roundtrip and hardware require separate checks",
    )
