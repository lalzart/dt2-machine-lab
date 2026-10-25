"""Active mod builds and resource declarations behind the shared lab CLI."""

import hashlib
import struct
import subprocess
import sys

from lab.context import BuildContext
from lab.dt2_116 import BASE, CANDIDATE_GAPS, OWNERSHIP_GAPS, STOCK_SHA
from lab.project import require, write_json
from lab.resources import patch_conflicts

MODS = ("sine", "plaits", "flex", "capicola", "arp")
RUNTIME_VARIANTS = ("reference", "trace-off", "cached", "cached-trace-off")


def resource_declarations():
    """Capacities are declarations, not a snapshot of live heap occupancy."""
    from lab.capicola_layout import STATE_BASE, STATE_BYTES
    from lab.capicola_memory import BANK_BASE

    return dict(
        schema="dt2-integration-resources-v1",
        firmware="Digitakt II OS1.16",
        records=[
            dict(owner="arp", space="cpu-heap", measure="requested", bytes=8192),
            dict(owner="arp", space="cpu-heap", measure="used-extent", bytes=4500),
            dict(owner="arp", space="cpu-heap", measure="rounded", bytes=8192),
            dict(
                owner="flex", space="cpu-heap", measure="descriptor-request", bytes=64
            ),
            dict(
                owner="flex",
                space="cpu-heap",
                measure="maximum-source-request",
                bytes=3840080,
            ),
            dict(
                owner="flex",
                space="cpu-heap",
                measure="maximum-source-rounded",
                bytes=4194304,
            ),
            dict(
                owner="flex",
                space="cpu-heap",
                measure="save-scratch-request",
                bytes=32768,
            ),
            dict(
                owner="capicola",
                space="sample-pool",
                measure="reserved",
                bytes=8 * 1024 * 1024,
            ),
            dict(
                owner="capicola",
                space="sample-pool",
                measure="bank-arena-within-reservation",
                bytes=STATE_BASE - BANK_BASE,
            ),
            dict(
                owner="capicola",
                space="sample-pool",
                measure="working-span-within-reservation",
                bytes=STATE_BYTES,
            ),
            dict(
                owner="capicola",
                space="dsp-lanes",
                measure="reader-state-within-working-span",
                bytes=8832,
            ),
            dict(
                owner="capicola",
                space="dsp-cache",
                measure="descriptor-state-within-working-span",
                bytes=1436,
            ),
        ],
        source_identity_limit=32,
        protected_heap_headroom=None,
        hardware_utilization=None,
        live_counters=None,
        note="Declared per-feature bounds; nested capacities are not additive or live usage",
    )


def cpu_plan(mods, output):
    require(mods and len(mods) == len(set(mods)), "Choose distinct mods")
    require(all(name in MODS for name in mods), "Unknown mod")
    require(
        not ("sine" in mods and "plaits" in mods), "SINE and Plaits both own machine:7"
    )
    if "capicola" in mods:
        mods = list(dict.fromkeys([*mods, "plaits", "flex"]))
    require(
        not ("sine" in mods and "plaits" in mods), "SINE and Plaits both own machine:7"
    )
    context = BuildContext.configured(output)
    stock = context.stock_main.read_bytes()
    require(hashlib.sha256(stock).hexdigest() == STOCK_SHA, "Unknown stock MAIN")
    modules, payload = [], {}
    for name in mods:
        if name == "arp":
            from lab.arp_firmware import patch_cpu

            _, report = patch_cpu(stock, tempo_ui=True)
        elif name == "flex":
            from lab.flex_native_build import patch_cpu

            _, report = patch_cpu(stock, managed_sources=True)
        elif name in ("plaits", "sine"):
            if name == "sine":
                from lab.cpu import build

                build()
                image = (output / "SINE_MAIN_OS.bin").read_bytes()
            else:
                from lab.plaits_cpu import build_cpu

                build_cpu(family="integration", output=output)
                image = (output / "PLAITS_MAIN_OS.bin").read_bytes()
            # Diff contiguous changed bytes; exact full stock identity above is mandatory.
            writes, pos = [], 0
            while pos < len(stock):
                if image[pos] == stock[pos]:
                    pos += 1
                    continue
                end = pos + 1
                while end < len(stock) and image[end] != stock[end]:
                    end += 1
                writes.append(
                    dict(address=BASE + pos, after=image[pos:end].hex(), label=name)
                )
                pos = end
            report = dict(writes=writes, locations={})
        else:
            from lab.capicola_memory import SITES

            writes = []
            for addr, opcode, old, new, label in SITES:
                expected = bytes.fromhex(opcode) + struct.pack(">I", old)
                require(
                    stock[addr - BASE : addr - BASE + 6] == expected,
                    "Pool reservation guard",
                )
                writes.append(
                    dict(
                        address=addr,
                        after=(bytes.fromhex(opcode) + struct.pack(">I", new)).hex(),
                        label=label,
                    )
                )
            report = dict(writes=writes, locations={})
        locations = set(report["locations"].values())
        payload[name] = sum(
            len(bytes.fromhex(w["after"]))
            for w in report["writes"]
            if w["address"] in locations
        )
        modules.append((name, report["writes"]))
    conflicts = patch_conflicts(modules)
    capacity = sum(hi - lo for lo, hi in CANDIDATE_GAPS + OWNERSHIP_GAPS) + (
        2108 if "arp" in mods else 0
    )
    fits = sum(payload.values()) <= capacity
    result = dict(
        schema="dt2-composition-plan-v1",
        firmware="Digitakt II OS1.16",
        mods=mods,
        compatible=not conflicts and fits,
        overlaps=conflicts,
        padding_bytes=capacity,
        payload_bytes=payload,
        raw_payloads_fit=fits,
        shared_save_dispatch_required="arp" in mods and "flex" in mods,
        unverified_memory_admitted=False,
        hardware_ready=False,
        limitation="Existing padding only. Shared-save code has native ABI tests; combined placement requires a validated additional region or proven code reduction.",
    )
    write_json(output / "resource-plan.json", result)
    write_json(output / "integration-resources.json", resource_declarations())
    return result


def build_mod(name, output, runtime_variant="reference", *, shared_save=False):
    require(name in MODS and name != "sine", "Use the original SINE builder")
    require(
        name == "capicola" or runtime_variant == "reference",
        "Runtime specialization belongs to Capicola",
    )
    context = BuildContext.configured(output)
    stock = context.stock_main.read_bytes()
    require(hashlib.sha256(stock).hexdigest() == STOCK_SHA, "Unknown stock MAIN")
    require(
        not shared_save or name in ("arp", "flex"),
        "Shared-save variants currently belong to Arp/Flex",
    )
    result = dict(
        ok=True,
        firmware="Digitakt II OS1.16",
        mod=name,
        output=str(output),
        hardware_ready=False,
    )
    if name == "arp":
        from lab.arp_firmware import patch_cpu

        image, result["cpu"] = patch_cpu(stock, tempo_ui=True, shared_save=shared_save)
    elif name == "flex":
        from lab.flex_native_build import patch_cpu

        image, result["cpu"] = patch_cpu(
            stock, managed_sources=True, shared_save=shared_save
        )
    else:
        from lab.dsp_build import build_blob
        from lab.plaits_cpu import build_cpu

        result["cpu"] = build_cpu(family="integration", output=output)
        image = (output / "PLAITS_MAIN_OS.bin").read_bytes()
        if name == "capicola":
            from lab.capicola_memory import patch_cpu as reserve
            from lab.flex_native_build import patch_cpu as flex
            from lab.plaits_menu import patch_cpu as menu

            image, result["flex"] = flex(image, managed_sources=True)
            image, result["menu"] = menu(image)
            image, result["reservation"] = reserve(image, managed_flex=True)
        family = "integration" if name == "plaits" else "capicola-stretch-live"
        blob = build_blob(
            True,
            family=family,
            layout="legacy" if name == "plaits" else "reserved-state",
            runtime_variant=runtime_variant,
            output=output / "dsp",
        )
        result["blob_sha256"] = hashlib.sha256(blob).hexdigest()
    (output / "MAIN_OS.bin").write_bytes(image)
    result["main_sha256"] = hashlib.sha256(image).hexdigest()
    write_json(output / "integration-resources.json", resource_declarations())
    return result


def test_mod(name, output, runtime_variant="reference", *, shared_save=False):
    context = BuildContext.configured(output)
    table = {
        "plaits": ("check-plaits-integration.py", []),
        "flex": ("check-flex-lifetime.py", ["--managed-sources", "--heap-trace"]),
        "arp": (
            "check-arp-firmware.py",
            [
                "--tempo-ui",
                "--tempo",
                "120",
                "--rate",
                "1/16",
                "--mode",
                "order",
                "--record",
                "--storage",
                "--instruction-limit",
                "12500000000",
            ],
        ),
        "capicola": (
            "check-capicola-stretch-live-native.py",
            ["--runtime-variant", runtime_variant],
        ),
    }
    require(
        runtime_variant in ("reference", "cached"),
        "Trace-disabled comparisons use labctl compare-runtime",
    )
    require(
        not shared_save or name in ("arp", "flex"),
        "Shared-save variants currently belong to Arp/Flex",
    )
    script, extra = table[name]
    if shared_save:
        extra = [*extra, "--shared-save"]
    child_output = output / "native"
    subprocess.run(
        [
            sys.executable,
            "-B",
            str(context.root / "scripts" / script),
            str(child_output),
            *extra,
        ],
        check=True,
    )
    return dict(
        ok=True,
        scope="See native child report for evidence boundary",
        output=str(child_output),
    )
