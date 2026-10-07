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


def build_payload(locations):
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
        "accept": (native.accept_recording(at("accept"), at("copy"), errors), "code"),
        "assign": (native.assign_recording(at("assign")), "code"),
    }
    save, after_open = native.save_recording(at("save"))
    payload["save"] = (save, "code")
    payload["exclusive_open"] = (
        native.exclusive_open_guard(at("exclusive_open"), after_open),
        "code",
    )
    payload["persist"] = (
        native.persist_project_pool(
            at("persist"), at("lookup"), at("save"), at("path_format"), at("directory")
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
        native.recorder_use_worker(at("use_worker"), at("state"), at("accept"), errors),
        "code",
    )
    payload["error_trampoline"] = (
        bytes.fromhex("4e56ffa4206e0008 4ef940021974"),
        "stock-trampoline",
    )
    payload["use_finish"] = (
        native.recorder_use_finish(
            at("use_finish"), at("state"), at("assign"), at("error_trampoline"), errors
        ),
        "code",
    )
    for key, text in {
        "save_title": "SAVE FLEX SAMPLE",
        "save_initial": "FLEX",
        "save_success": "FLEX: SAMPLE SAVED",
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
    payload["save_promote"] = (named.promote(at("save_promote")), "code")
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
    return payload


def patch_cpu(image):
    baseline = hashlib.sha256(image).hexdigest()
    require(
        baseline in (STOCK_SHA, R3_SHA),
        "Native Flex requires exact stock 1.16 or audited Plaits R3",
    )
    data, writes = bytearray(image), []
    gaps = [list(g) for g in CANDIDATE_GAPS]
    for lo, hi in gaps:
        require(BASE <= lo < hi <= 0x403117C4, "Invalid native Flex placement")
        require(
            not any(data[lo - BASE : hi - BASE]),
            f"Occupied native Flex padding {lo:#x}",
        )
    locations = {}
    sizes = {key: len(value[0]) for key, value in build_payload({}).items()}
    for key, length in sorted(sizes.items(), key=lambda item: (-item[1], item[0])):
        choices = [(hi - lo, i) for i, (lo, hi) in enumerate(gaps) if hi - lo >= length]
        require(choices, f"Native Flex padding exhausted: {key}")
        _, index = min(choices)
        locations[key] = gaps[index][0]
        gaps[index][0] += (length + 3) & ~3

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

    for key, (code, kind) in build_payload(locations).items():
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
        writes=writes,
        payload_bytes=sum(sizes.values()),
        status="experimental-native-image",
        hardware_ready=False,
        scope="Native device instructions; boot, UI scheduling, full project roundtrip and hardware require separate checks",
    )
