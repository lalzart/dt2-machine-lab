#!/usr/bin/env python3
"""Trace actual OS 1.16 loader/resource instructions; peripheral calls are modeled."""

# ruff: noqa: E402
import argparse
import hashlib
import json
import os
import struct
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lab.project import doctor, require, settings, sha256, write_json

config = settings()
if Path(sys.executable).resolve() != config["python"].resolve():
    os.execv(str(config["python"]), [str(config["python"]), __file__, *sys.argv[1:]])
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("output", type=Path)
p.add_argument("--frames", type=int, default=1025)
p.add_argument("--stereo", action="store_true")
p.add_argument("--compact-resources", action="store_true")
p.add_argument("--separate-source", action="store_true")
p.add_argument("--managed-sources", action="store_true")
p.add_argument("--cycles", type=int, default=1)
p.add_argument("--heap-trace", action="store_true")
p.add_argument(
    "--snapshot",
    type=Path,
    default=ROOT.parent
    / "Digitect firmware research project/work/digikit/snapshots/dt2-1.16/running.snap",
)
p.add_argument("--shared-save", action="store_true")
p.add_argument("--cpu-extension", action="store_true", help="Prepared-fixture component test; cold reset is checked separately")
p.add_argument("--package", type=Path, help="Check the exact CPU image from a local extension package")
args = p.parse_args()
if args.package:
    args.cpu_extension = args.managed_sources = True
require(not args.cpu_extension or args.managed_sources, "Extension uses managed sources")
if args.managed_sources:
    args.compact_resources = args.separate_source = True
require(
    1 <= args.cycles <= 32 and args.frames + args.cycles - 1 <= 960000,
    "Cycle fixture exceeds registered limits",
)
require(
    args.cycles == 1 or args.managed_sources,
    "Repeated fixture requires managed sources",
)
doctor()
require(
    sha256(args.snapshot)
    == "175982f14b371fafe0eb54f2943167a94f71370327e65c7fe9941b1336bbc301",
    "Unknown snapshot",
)
out = args.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use out/runs")
out.mkdir(parents=True, exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))
# Runtime configures the pinned dependency import path before those imports.
from lab.runtime import STOCK_MAIN  # isort: skip

import plusdrive_check as check
import tools.plusdrive as pd
from unicorn import UC_HOOK_CODE
from unicorn import m68k_const as k

from lab.flex_memory import ENTRY
from lab.flex_memory import patch_cpu as patch_accounting
from lab.flex_native import RESOURCE_SITES
from lab.flex_native_build import BASE, patch_cpu

samples = out / "samples"
samples.mkdir()
with wave.open(str(samples / "fixture.wav"), "wb") as wav:
    wav.setparams((1, 2, 48000, 0, "NONE", "not compressed"))
    wav.writeframes(bytes(512))
card = out / "card.img"
entries = pd.build(str(samples), str(card), main_os=STOCK_MAIN.read_bytes())


class TracedFirmware(check.Firmware):
    def _flexbus_page(self, arg):
        trace.append(dict(event="transfer", args=[arg(i) for i in range(3)]))
        return super()._flexbus_page(arg)

    def _loader_event(self, arg):
        trace.append(dict(event="event", args=[arg(0), arg(1)]))
        return super()._loader_event(arg)


fw = TracedFirmware(card, args.snapshot, STOCK_MAIN)
trace = []
report = {
    "status": "running",
    "scope": __doc__,
    "frames": args.frames,
    "stereo": args.stereo,
    "snapshot": sha256(args.snapshot),
    "source_sha256": sha256(ROOT / "lab/flex_native.py"),
}


def pcm(first, count):
    return b"".join(
        struct.pack(">H", v)
        for i in range(first, first + count)
        for v in (
            (i * 17 & 65535, (30000 - i * 29) & 65535)
            if args.stereo
            else (i * 17 & 65535,)
        )
    )


def service(arg):
    command, mono, first, count = struct.unpack(">HHII", fw.read(arg(1), 12))
    require(command == 4 and mono == int(not args.stereo), "Recorder request")
    fw.write(0x4FE79340, pcm(first, count).ljust(2048, b"\xe7"))
    return 0


heap_trace = None
try:
    fw.call(0x40154358, [])
    check.check_mount(fw, entries[0]["ref"])
    if args.cpu_extension:
        from lab.cpu_extension import build_cpu

        def patch_cpu(stock, **options):
            if args.package:
                from lab.cpu_fixture import load_package

                image, combined, _manifest = load_package(args.package)
            else:
                image, combined = build_cpu(stock)
            return image, dict(combined, locations=combined["flex"]["locations"])

    image, meta = patch_cpu(
        STOCK_MAIN.read_bytes(),
        compact_resources=args.compact_resources,
        separate_source=args.separate_source,
        memory_accounting=args.separate_source,
        managed_sources=args.managed_sources,
        shared_save=args.shared_save,
    )
    report["compact_resources"] = args.compact_resources
    loc = meta["locations"]
    if args.cpu_extension:
        from lab.cpu_fixture import install as install_cpu

        install_cpu(fw.write, image, meta, read=fw.read)
    else:
        for w in meta["writes"]:
            old = bytes.fromhex(w["before"])
            require(fw.read(w["address"], len(old)) == old, "Patch guard")
            fw.write(w["address"], bytes.fromhex(w["after"]))
    if args.cpu_extension:
        # Both components inhabit this actual image. Exercise Arp initialization
        # against the same native heap as Flex before its lifecycle scenario.
        fw.call(meta['arp']['locations']['ensure'], [])
        arp_state = fw.u32(meta['arp']['locations']['pointer'])
        require(arp_state != 0, 'Combined Arp native initialization failed')
        report['cpu_extension'] = dict(main_sha256=meta['sha256'], arp_state=arp_state,
                                       reservation=meta['reservation'])
    if args.separate_source:
        accounting_entry = loc["memory_snapshot"]
        accounting = dict(
            entry=accounting_entry,
            separate_source=True,
            source_retirement=args.managed_sources,
        )
    else:
        image, accounting = patch_accounting(image)
        accounting_entry = ENTRY
        fw.write(ENTRY, image[ENTRY - BASE : ENTRY - BASE + accounting["bytes"]])
    report["accounting_overlay"] = accounting
    report["main_sha256"] = hashlib.sha256(image).hexdigest()
    write_json(out / "native-patches.json", meta)
    report["sources"] = {
        p: sha256(ROOT / p)
        for p in (
            "lab/flex_native.py",
            "lab/flex_native_build.py",
            "lab/flex_native_save.py",
            "lab/flex_resources.py",
            "lab/flex_retirement.py",
            "lab/flex_memory.py",
            "scripts/check-flex-lifetime.py",
        )
    }
    fw.uc.ctl_remove_cache(BASE, BASE + len(image))
    fw._hle(0x400124A0, service)
    sites = {v[0]: key for key, v in RESOURCE_SITES.items()}
    sites.update({check.LOAD_SAMPLE: "loader"})

    def enter(uc, pc, size, data):
        sp = uc.reg_read(k.UC_M68K_REG_A7)
        a = [fw.u32(sp + i) for i in (4, 8, 12)]
        trace.append(
            dict(event=sites[pc], pc=hex(pc), args=a, return_pc=hex(fw.u32(sp)))
        )

    for pc in sites:
        fw.uc.hook_add(UC_HOOK_CODE, enter, begin=pc, end=pc)
    if args.heap_trace:
        from lab.flex_heap import HeapTrace

        heap_trace = HeapTrace(fw)
        report["sources"]["lab/flex_heap.py"] = sha256(ROOT / "lab/flex_heap.py")
        heap_trace.phase = "accept"
    node = fw.call(
        loc["accept"],
        [loc["state"], 0, args.frames, int(args.stereo), 300],
        limit=800000000,
    )
    require(node != 0xFFFFFFFF, "accept failed")
    source = fw.u32(node + 20)
    length = fw.u32(node + 12)
    original = fw.read(source, length)
    counters = fw.alloc(16)
    require(fw.call(accounting_entry, [loc["state"], counters]) == 0, "accounting")
    expected_counters = (1, 0, length - 80, length + 64)
    require(
        struct.unpack(">4I", fw.read(counters, 16)) == expected_counters,
        "Accounting disagrees with actual retained source",
    )
    report["accounting_after_accept"] = list(expected_counters)
    data_pages = [v for v in fw.pages if v[0] != 0xFFFFFFFF]
    headers = [struct.unpack_from(">5I", v[1]) for v in fw.pages if v[0] == 0xFFFFFFFF]
    # Existing helper expects slot,startL,startR,rate,len (five words).
    loaded = {"pages": data_pages, "slot_headers": [h[:5] for h in headers]}
    matches = check.sent_pcm_matches(loaded, original)
    require(all(matches), "Transferred PCM differs")
    report.update(
        node=hex(node),
        source=hex(source),
        bytes=length,
        pcm_equal=matches,
        resource_events={
            n: sum(e["event"] == n for e in trace) for n in sites.values()
        },
    )
    reads = []
    # This runtime's M68K memory-read hook does not observe these accesses.
    # Count the actual emitted MOVE.B source-read instruction instead.
    read_parts = [
        w
        for w in meta["writes"]
        if w["label"].split("/")[-1]
        in (
            ("resource_dispatch", "resource_dispatch_1", "resource_dispatch_2")
            if args.compact_resources
            else ("read",)
        )
    ]
    read_part = next(
        w for w in read_parts if bytes.fromhex("12d8") in bytes.fromhex(w["after"])
    )
    read_code = bytes.fromhex(read_part["after"])
    require(read_code.count(bytes.fromhex("12d8")) == 1, "Unique read-loop instruction")
    read_pc = read_part["address"] + read_code.index(bytes.fromhex("12d8"))

    def watch(uc, pc, size, data):
        reads.append(uc.reg_read(k.UC_M68K_REG_A0))

    hook = fw.uc.hook_add(UC_HOOK_CODE, watch, begin=read_pc, end=read_pc)
    fw.pages.clear()
    result = fw.call(check.LOAD_SAMPLE, [node + 4, 301], limit=800000000)
    require(result == 0, "alias load")
    report["alias_source_reads"] = len(reads)
    report["alias_pages"] = len([p for p in fw.pages if p[0] != 0xFFFFFFFF])
    # Future explicit source opens still require RAM even after successful load.
    handle = fw.alloc(16)
    dest = fw.alloc(128)
    require(fw.call(RESOURCE_SITES["open"][0], [node + 4, handle]) == 0, "open")
    before = len(reads)
    require(fw.call(RESOURCE_SITES["read"][0], [dest, 128, handle]) == 128, "read")
    require(fw.read(dest, 128) == original[:128], "source read bytes")
    report["post_loader_open_reads"] = len(reads) - before
    require(
        reads[before:] == list(range(source, source + 128)),
        "Read instrumentation missed accesses",
    )
    fw.write(source, b"\xa5" * length)
    fw.write(handle + 4, bytes(4))
    require(
        fw.call(RESOURCE_SITES["read"][0], [dest, 128, handle]) == 128, "negative read"
    )
    report["early_release_negative_detected"] = fw.read(dest, 128) != original[:128]
    require(report["early_release_negative_detected"], "negative control missed")
    fw.write(source, original)
    fw.uc.hook_del(hook)
    # Exercise actual stock unload/reset, then reload the immutable source.
    for slot in (300, 301):
        fw.call(0x401540C6, [slot])
        fw.call(0x40153BEA, [slot])
        require(fw.u32(check.LOADER_LEN + slot * 4) == 0, "Slot length not cleared")
    # A previously opened source handle still owns a future read even after
    # the two actual stock slot teardown calls. Slot emptiness is insufficient.
    fw.write(handle + 4, bytes(4))
    require(
        fw.call(RESOURCE_SITES["read"][0], [dest, 128, handle]) == 128,
        "Delayed read after stock slot clear",
    )
    require(fw.read(dest, 128) == original[:128], "Delayed reader lost source")
    fw.call(RESOURCE_SITES["close"][0], [handle])
    report["delayed_source_handle_survives_slot_clear"] = True
    fw.pages.clear()
    require(fw.call(check.LOAD_SAMPLE, [node + 4, 302], limit=800000000) == 0, "reload")
    loaded = {
        "pages": [v for v in fw.pages if v[0] != 0xFFFFFFFF],
        "slot_headers": [
            struct.unpack_from(">5I", v[1]) for v in fw.pages if v[0] == 0xFFFFFFFF
        ],
    }
    require(all(check.sent_pcm_matches(loaded, original)), "Reload PCM differs")
    report["stock_clear_then_reload_pcm_equal"] = True
    require(
        fw.call(accounting_entry, [loc["state"], counters]) == 0,
        "accounting after clear",
    )
    require(
        struct.unpack(">4I", fw.read(counters, 16)) == expected_counters,
        "Stock unload must not pretend to reclaim Flex source",
    )
    report["accounting_after_clear_reload"] = list(expected_counters)
    if heap_trace:
        heap_trace.phase = "save-handover"
    if args.managed_sources:
        # Keep a synthetic handle across save-backed source retirement.
        require(
            fw.call(RESOURCE_SITES["open"][0], [node + 4, handle]) == 0, "late handle"
        )
        pool = fw.alloc(b"\xff" * (1024 * 16))
        fw.write(pool + 16, fw.read(node + 4, 16))
        frees = []

        def freed(uc, pc, size, data):
            frees.append(fw.u32(uc.reg_read(k.UC_M68K_REG_A7) + 4))

        free_hook = fw.uc.hook_add(
            UC_HOOK_CODE, freed, begin=0x4011E8FC, end=0x4011E8FC
        )
        require(fw.call(loc["pin_source"], [node]) == source, "pin before save")
        require(
            fw.call(loc["persist"], [pool], limit=800000000) == 0,
            "persist and handover",
        )
        require(fw.u32(node + 20) == source, "Save freed an active source")
        require(fw.call(loc["unpin_source"], [node]) == 0, "unpin saved source")
        durable = fw.read(node + 32, 16)
        for word in range(5):
            corrupt = bytearray(durable)
            if word == 4:
                corrupt[:] = b"\xff" * 16
            else:
                corrupt[word * 4 + 3] ^= 2
            fw.write(node + 32, corrupt)
            require(
                fw.call(loc["retire_source"], [node]) == 1
                and fw.u32(node + 20) == source
                and source not in frees,
                "Invalid backing released the only source",
            )
        fw.write(node + 32, durable)
        require(fw.call(loc["retire_source"], [node]) == 0, "Exact handover")
        report["invalid_backing_retains_source"] = True
        require(
            fw.u32(node + 20) == 0 and fw.u32(node + 48) == 0,
            "RAM source still retained",
        )
        require(
            source in frees and node not in frees, "Source/descriptor free boundary"
        )
        require(
            fw.call(accounting_entry, [loc["state"], counters]) == 0,
            "post-save accounting",
        )
        require(
            struct.unpack(">4I", fw.read(counters, 16)) == (1, 1, 0, 64),
            "Retired source accounting",
        )
        require(
            fw.call(RESOURCE_SITES["read"][0], [dest, 128, handle]) == 128,
            "late backed read",
        )
        require(fw.read(dest, 128) == original[:128], "Late handle PCM mismatch")
        # Saving again reads a bounded temporary copy of the durable source.
        path = fw.alloc(b"/recorded/RETIRED-SAVE-AS\0")
        saved_ref = fw.alloc(16)
        require(
            fw.call(loc["save"], [node, path, saved_ref], limit=800000000) == 0,
            "save after retirement",
        )
        require(
            fw.call(loc["save_promote"], [node, pool, saved_ref]) == 0,
            "promote save-as",
        )
        require(
            fw.u32(node + 20) == 0 and fw.u32(node + 48) == 0, "Save-as resurrected RAM"
        )
        fw.write(handle + 4, struct.pack(">I", 128))
        require(
            fw.call(RESOURCE_SITES["read"][0], [dest, 128, handle]) == 128,
            "late handle after save-as",
        )
        require(fw.read(dest, 128) == original[128:256], "Save-as late PCM mismatch")
        cached = fw.read(node + 32, 16)
        before_writes = len(fw.card.writes)
        failed_path = fw.alloc(b"/recorded/STALE-BACKING-MUST-FAIL\0")
        failed_ref = fw.alloc(b"\xcc" * 16)
        old_pool_ref = fw.read(pool + 16, 16)
        for word in range(5):
            corrupt = bytearray(cached)
            if word == 4:
                corrupt[:] = b"\xff" * 16
            else:
                corrupt[word * 4 + 3] ^= 2
            fw.write(node + 32, corrupt)
            fw.write(dest, b"\xcc" * 128)
            require(
                fw.call(loc["read_backing"], [node, dest, 128, 0]) == 0xFFFFFFFF
                and fw.read(dest, 128) == b"\xcc" * 128,
                "Mismatched backing read data",
            )
            require(
                fw.call(loc["save"], [node, failed_path, failed_ref], limit=800000000)
                == 0xFFFFFFFF,
                "Stale backing unexpectedly saved",
            )
            require(
                fw.read(failed_ref, 16) == b"\xcc" * 16
                and len(fw.card.writes) == before_writes,
                "Stale backing modified storage or output reference",
            )
            fw.write(pool + 16, fw.read(node + 4, 16))
            bad_pool = fw.read(pool, 1024 * 16)
            require(
                fw.call(loc["persist"], [pool]) == 0xFFFFFFFF
                and fw.read(pool, 1024 * 16) == bad_pool,
                "Stale backing was committed to project",
            )
        fw.write(pool + 16, old_pool_ref)
        fw.write(node + 32, cached)
        report["stale_backing_rejected_without_publication"] = True
        report["corrupted_reference_words_rejected"] = 4
        report["missing_backing_rejected"] = True
        fw.pages.clear()
        # Force the stock loader to consume backing rather than an existing alias.
        fw.call(0x401540C6, [302])
        fw.call(0x40153BEA, [302])
        require(
            fw.call(check.LOAD_SAMPLE, [node + 4, 303], limit=800000000) == 0,
            "backed reload",
        )
        backed = {
            "pages": [v for v in fw.pages if v[0] != 0xFFFFFFFF],
            "slot_headers": [
                struct.unpack_from(">5I", v[1]) for v in fw.pages if v[0] == 0xFFFFFFFF
            ],
        }
        require(
            all(check.sent_pcm_matches(backed, original)), "Backed reload PCM differs"
        )
        fw.call(RESOURCE_SITES["close"][0], [handle])
        fw.uc.hook_del(free_hook)
        report["managed_handover"] = dict(
            source_freed=True,
            descriptor_retained=True,
            late_handle_reads=True,
            save_as_after_retirement=True,
            stock_backed_reload_pcm_equal=True,
            accounting_after_save=[1, 1, 0, 64],
        )
        source_addresses = [source]
        if heap_trace:
            heap_trace.phase = "sequential-reuse"
        for index in range(1, args.cycles):
            fw.pages.clear()
            new_node = fw.call(
                loc["accept"],
                [loc["state"], index, args.frames, int(args.stereo), 400 + index],
                limit=800000000,
            )
            require(new_node != 0xFFFFFFFF, "Sequential acceptance failed")
            source_addresses.append(fw.u32(new_node + 20))
            fw.write(pool + (index + 1) * 16, fw.read(new_node + 4, 16))
            require(
                fw.call(loc["persist"], [pool], limit=800000000) == 0,
                "Sequential persistence failed",
            )
            require(fw.u32(new_node + 20) == 0, "Sequential source not retired")
            require(
                fw.call(accounting_entry, [loc["state"], counters]) == 0,
                "Sequential accounting",
            )
            require(
                struct.unpack(">4I", fw.read(counters, 16))
                == (index + 1, index + 1, 0, 64 * (index + 1)),
                "Source bytes accumulated",
            )
        require(
            fw.call(RESOURCE_SITES["open"][0], [node + 4, handle]) == 0,
            "First identity survived reuse",
        )
        require(
            fw.call(RESOURCE_SITES["read"][0], [dest, 128, handle]) == 128
            and fw.read(dest, 128) == original[:128],
            "First immutable take changed",
        )
        fw.call(RESOURCE_SITES["close"][0], [handle])
        report["sequential_reuse"] = dict(
            cycles=args.cycles,
            retained_source_bytes=0,
            retained_descriptor_bytes=args.cycles * 64,
            distinct_source_addresses=len(set(source_addresses)),
            first_take_unchanged=True,
            more_than_32_supported=False,
        )
        if args.cycles == 32:
            require(
                fw.call(
                    loc["accept"], [loc["state"], 0, args.frames, int(args.stereo), 450]
                )
                == 0xFFFFFFFF
                and fw.u32(loc["state"] + 4) == 32,
                "Identity ceiling was bypassed",
            )
            report["sequential_reuse"]["thirty_third_rejected"] = True
    report["status"] = "PASS"
except Exception as exc:
    report["status"] = "FAIL"
    report["error"] = str(exc)
    raise
finally:
    if heap_trace:
        report["heap_trace"] = heap_trace.report()
        require(report["heap_trace"]["pending_calls"] == 0, "Unfinished heap calls")
    write_json(out / "report.json", report)
    (out / "loader-lifecycle.jsonl").write_text(
        "".join(json.dumps(e) + "\n" for e in trace)
    )
    fw.close()
print(json.dumps(report, indent=2))
