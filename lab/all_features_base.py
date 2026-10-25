"""Reproduce the reviewed Plaits/CAPI CPU image and retire its old Flex slots.

No Plaits relocation or new DSP algorithm is introduced. The small early
loader uses a separate reviewed cave; Arp and Flex use the DDR extension.
"""

import hashlib
import json

from lab.dt2_116 import BASE, STOCK_SHA
from lab.project import require

LEGACY_SHA = "7f911a1e68158f991f9327d8cfae10a143824959f319b930eb4f3e40a9cba989"
BASE_SHA = "8d01d11a3ed1e26456c63a98c80e2ee57440e14d2bbedacba6b013e0d59fb5e3"
LOADER = 0x402FC718


def build_base(stock, output):
    from lab.capicola_memory import patch_cpu as reserve
    from lab.capicola_toggle import ARENA, SOURCE_ARENA
    from lab.capicola_toggle import patch_cpu as toggle
    from lab.flex_native_build import patch_cpu as flex
    from lab.plaits_cpu import build_cpu
    from lab.plaits_menu import patch_cpu as menu

    require(hashlib.sha256(stock).hexdigest() == STOCK_SHA, "Unknown all-feature stock")
    output.mkdir(parents=True, exist_ok=True)
    plaits_report = build_cpu(family="integration", output=output)
    plaits = (output / "PLAITS_MAIN_OS.bin").read_bytes()
    original_flex, flex_report = flex(plaits, managed_sources=True)
    ordered, menu_report = menu(original_flex)
    reserved, reservation = reserve(ordered, managed_flex=True)
    legacy, capi = toggle(reserved)
    require(
        hashlib.sha256(legacy).hexdigest() == LEGACY_SHA, "Legacy combination drift"
    )
    (output / "RESERVED_NO_TOGGLE_MAIN.bin").write_bytes(reserved)
    (output / "LEGACY_TOGGLE_MAIN.bin").write_bytes(legacy)
    data = bytearray(legacy)
    for w in reversed(flex_report["writes"]):
        off = w["address"] - BASE
        before, after = bytes.fromhex(w["before"]), bytes.fromhex(w["after"])
        require(
            data[off : off + len(after)] == after,
            "Retired Flex byte guard " + w["label"],
        )
        data[off : off + len(after)] = before
    require(hashlib.sha256(data).hexdigest() == BASE_SHA, "Stripped CPU base drift")
    # Prove the retirement is completely reversible and affects only old Flex.
    rebuilt = bytearray(data)
    for w in flex_report["writes"]:
        off = w["address"] - BASE
        before, after = bytes.fromhex(w["before"]), bytes.fromhex(w["after"])
        require(
            rebuilt[off : off + len(before)] == before, "Flex retirement reverse guard"
        )
        rebuilt[off : off + len(after)] = after
    require(rebuilt == legacy, "Retirement changed unrelated CPU bytes")
    require(not any(data[LOADER - BASE : LOADER - BASE + 68]), "Loader cave occupied")

    # Byte ranges describe an exact hash-authenticated pre-existing image,
    # including partial inline operands. They are not newly emitted code.
    # Audit/classification of that image remains in the original R3 reports.
    padded = stock + bytes(len(data) - len(stock))
    writes, cursor = [], 0
    while cursor < len(data):
        if data[cursor] == padded[cursor]:
            cursor += 1
            continue
        end = cursor + 1
        while end < len(data) and data[end] != padded[end]:
            end += 1
        address = BASE + cursor
        record = dict(
            address=address,
            before=padded[cursor:end].hex(),
            after=bytes(data[cursor:end]).hex(),
            label="plaits-capi/base",
            kind="validated-base",
            payload=False,
        )
        if address >= SOURCE_ARENA:
            record["runtime_address"] = ARENA + address - SOURCE_ARENA
        writes.append(record)
        cursor = end
    initializers = [
        dict(
            address=w["runtime_address"],
            after=w["after"],
            mutable=w["mutable"],
            label=w["label"],
        )
        for w in capi["writes"]
        if "runtime_address" in w
    ]
    report = dict(
        sha256=BASE_SHA,
        legacy_sha256=LEGACY_SHA,
        plaits=plaits_report,
        plaits_integration=json.loads(
            (output / "integration-cpu-patches.json").read_text()
        ),
        menu=menu_report,
        reservation=reservation,
        capi_toggle=capi,
        retired_flex_writes=len(flex_report["writes"]),
        retirement_reversible=True,
        writes=writes,
        runtime_initializers=initializers,
        loader_address=LOADER,
    )
    (output / "PLAITSCAPI_NOFLEX_MAIN.bin").write_bytes(data)
    (output / "base-patches.json").write_text(json.dumps(report, indent=2) + "\n")
    return bytes(data), report
