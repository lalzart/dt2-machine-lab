#!/usr/bin/env python3
# ruff: noqa: E402
"""Execute native Flex primitives and the stock OS 1.16 sample loader.

Applies the exact image overlay to a prepared CPU snapshot. Exercises original
project serialization and stock reload. Native UI scheduling and fresh boot
are separate checks.
Only recorder service, mutex,
eMMC, loader event and FlexBus peripheral boundaries use host models.
"""

import argparse
import hashlib
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
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("output", type=Path)
parser.add_argument("--snapshot", type=Path, required=True)
parser.add_argument("--managed-sources", action="store_true")
args = parser.parse_args()
doctor()
require(
    sha256(args.snapshot)
    == "175982f14b371fafe0eb54f2943167a94f71370327e65c7fe9941b1336bbc301",
    "Unknown isolated OS 1.16 snapshot",
)
out = args.output.resolve()
require(out.is_relative_to(ROOT / "out/runs"), "Use ignored run directory")
out.mkdir(parents=True, exist_ok=False)
os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))
# isort: off
from lab.runtime import STOCK_MAIN
from lab.flex_native import MAX_FRAMES, USE_ERRORS
import plusdrive_check as check
import tools.plusdrive as pd
from unicorn import UC_HOOK_CODE
from unicorn import m68k_const as k
# isort: on


class ObservedFirmware(check.Firmware):
    """Keep hook handles so a peripheral model replaces, not doubles, a stub."""

    def __init__(self, *args):
        super().__init__(*args)
        self.erases = []
        # CMD35/CMD36/CMD38 eMMC discard boundary, used by stock file deletion.
        # The guest filesystem and its allocation updates continue to execute.
        self._hle(0x4012DDF2, self.erase)

    def erase(self, arg):
        sector, count = arg(0), arg(1)
        require(
            sector >= 0x5EE180 and 0 < count <= 4096 and count % 64 == 0,
            "Unexpected content discard extent",
        )
        self.card.write(sector, bytes(count * 512))
        self.erases.append((sector, count))
        return 0

    def _hle(self, address, fn):
        if not hasattr(self, "service_hooks"):
            self.service_hooks = {}
        if address in self.service_hooks:
            self.uc.hook_del(self.service_hooks.pop(address))

        def hook(uc, _address, _size, _data):
            sp = uc.reg_read(k.UC_M68K_REG_A7)
            ret = self.u32(sp)
            result = fn(lambda i: self.u32(sp + 4 + i * 4))
            uc.reg_write(k.UC_M68K_REG_D0, (result or 0) & 0xFFFFFFFF)
            uc.reg_write(k.UC_M68K_REG_A7, sp + 4)
            uc.reg_write(k.UC_M68K_REG_PC, ret)

        self.service_hooks[address] = self.uc.hook_add(
            UC_HOOK_CODE, hook, begin=address, end=address
        )


def install(fw):
    from lab.flex_native_build import BASE, patch_cpu

    image, metadata = patch_cpu(
        STOCK_MAIN.read_bytes(), managed_sources=args.managed_sources
    )
    for patch in metadata["writes"]:
        address = patch["address"]
        before, after = bytes.fromhex(patch["before"]), bytes.fromhex(patch["after"])
        require(
            fw.read(address, len(before)) == before,
            f"Snapshot native patch guard: {patch['label']}",
        )
        fw.write(address, after)
    fw.uc.ctl_remove_cache(BASE, BASE + len(image))
    (out / "FLEX_MAIN_OS.bin").write_bytes(image)
    write_json(out / "native-patches.json", metadata)
    locations = metadata["locations"]
    return (
        *(locations[key] for key in ("state", "accept", "assign", "save", "persist")),
        locations,
    )


def pcm(start, frames, stereo):
    return struct.pack(
        ">" + "H" * frames * (2 if stereo else 1),
        *[
            v
            for i in range(start, start + frames)
            for v in (
                (i * 17 & 65535, (30000 - i * 29) & 65535)
                if stereo
                else (i * 17 & 65535,)
            )
        ],
    )


report = dict(
    status="running",
    scope=__doc__,
    firmware="OS 1.16",
    main_sha256=sha256(STOCK_MAIN),
    snapshot_sha256=sha256(args.snapshot),
    sources={
        p: sha256(ROOT / p)
        for p in (
            "lab/flex_native.py",
            "lab/flex_native_save.py",
            "lab/flex_native_build.py",
            "scripts/probe-flex-native.py",
            "lab/coldfire.py",
        )
    },
    cases=[],
)
try:
    for stereo in (False, True):
        folder = out / ("stereo" if stereo else "mono")
        samples = folder / "samples"
        samples.mkdir(parents=True)
        start, frames = 86, 2948
        payload = pcm(start, frames, stereo)
        wav_data = b"".join(payload[i : i + 2][::-1] for i in range(0, len(payload), 2))
        with wave.open(str(samples / "reference.wav"), "wb") as wav:
            wav.setparams((2 if stereo else 1, 2, 48000, 0, "NONE", "not compressed"))
            wav.writeframes(wav_data)
        card = folder / "card.img"
        entries = pd.build(str(samples), str(card), main_os=STOCK_MAIN.read_bytes())
        native = ObservedFirmware(card, args.snapshot, STOCK_MAIN)
        stock = check.Firmware(card, args.snapshot, STOCK_MAIN)
        try:
            for fw in (native, stock):
                fw.call(0x40154358, [])
                check.check_mount(fw, entries[0]["ref"])
            head, accept, assign, saver, persist, patches = install(native)
            # Stock-reference load after entry patches exercises all fallback paths.
            fallback = check.check_load(native, entries[0]["ref"], 1)
            reference = check.check_load(stock, entries[0]["ref"], 1)
            require(
                fallback["load_d0"] == reference["load_d0"] == 0,
                "Stock fallback failed",
            )
            require(native.pages == stock.pages, "Patched stock publication changed")
            native.card.reads.clear()
            native.card.writes.clear()
            depth, requests = [0], []

            def lock(arg, depth=depth):
                if arg(0) == 0x40965B74:
                    depth[0] += 1
                return 1

            def unlock(arg, depth=depth, native=native):
                if arg(0) == 0x40965B74:
                    require(depth[0] > 0, "Unbalanced recorder lock")
                    depth[0] -= 1
                    if not depth[0]:
                        native.write(0x4FE79340, b"\xa5" * 2048)
                return 0

            def service(
                arg, native=native, stereo=stereo, depth=depth, requests=requests
            ):
                require(arg(0) == 12 and arg(2) == 2048, "Recorder descriptor extent")
                command, mono, first, count = struct.unpack(
                    ">HHII", native.read(arg(1), 12)
                )
                require(command == 4 and mono == int(not stereo), "Recorder command")
                require(depth[0] == 2, "Outer lock lost")
                data = pcm(first, count, stereo)
                require(len(data) <= 2048, "Recorder response overflow")
                native.write(0x4FE79340, data.ljust(2048, b"\xe7"))
                requests.append((first, count, mono))
                return 0

            # Replace the inherited no-op recursive-mutex hooks with observers.
            native._hle(0x40001608, lock)
            native._hle(0x4000172A, unlock)
            native._hle(0x400124A0, service)
            for slot, count in (
                (1, frames),
                (128, frames),
                (300, 140),
                (300, MAX_FRAMES + 1),
            ):
                result = native.call(accept, [head, start, count, int(stereo), slot])
                require(
                    result == 0xFFFFFFFF and native.u32(head) == 0,
                    "Invalid acceptance mutated ownership",
                )
                require(not requests, "Invalid acceptance read recorder")
            # Native failure path after original heap allocation and recorder copy.
            native._hle(check.LOAD_SAMPLE, lambda arg: 1)
            result = native.call(accept, [head, start, frames, int(stereo), 300])
            if args.managed_sources:
                failed_node = native.u32(head)
                require(
                    result == 0xFFFFFFFF
                    and failed_node != 0
                    and native.u32(head + 4) == 1
                    and native.u32(failed_node + 20) == 0
                    and native.u32(failed_node + 56) == 1,
                    "Failed loader did not retire source and preserve tombstone",
                )
            else:
                require(
                    result == 0xFFFFFFFF
                    and native.u32(head) == 0
                    and native.u32(head + 4) == 0,
                    "Failed loader retained resource",
                )
            require(
                native.u32(head + 48) == list(USE_ERRORS).index("load")
                and native.u32(head + 52) == 1,
                "Loader failure lost its diagnostic reason",
            )
            require(
                native.u32(check.LOADER_LEN + 300 * 4) == 0, "Failed slot not cleared"
            )
            native.uc.hook_del(native.service_hooks.pop(check.LOAD_SAMPLE))
            requests.clear()
            native.pages.clear()
            node = native.call(accept, [head, start, frames, int(stereo), 300])
            require(
                node != 0xFFFFFFFF
                and native.u32(head) == node
                and native.u32(head + 4) == (2 if args.managed_sources else 1),
                "Native acceptance failed",
            )
            data_address = native.u32(node + 20)
            result = native.u32(node + 12)
            expected = pd.build_native_sample(payload, stereo)
            require(result == len(expected), "Native copy failed")
            require(
                native.read(data_address, result) == expected,
                "Native copy bytes differ",
            )
            require(
                native.u32(node + 8) == pd.content_hash(expected) | 1,
                "Native content hash differs from stock file format",
            )
            require(depth[0] == 0, "Recorder lock leaked")
            loaded = dict(
                load_d0=0,
                pages=[p for p in native.pages if p[0] != 0xFFFFFFFF],
                slot_headers=[
                    struct.unpack_from(">IIIII", p[1])
                    for p in native.pages
                    if p[0] == 0xFFFFFFFF
                ],
                events=native.events,
                len=native.u32(check.LOADER_LEN + 300 * 4),
                rate=native.u32(check.LOADER_RATE + 300 * 4),
                stereo=int(stereo),
            )
            loaded["data_pages"] = len(loaded["pages"])
            require(
                all(check.sent_pcm_matches(loaded, expected)), "Published PCM differs"
            )
            require(
                not native.card.reads and not native.card.writes,
                "Temporary load touched storage",
            )
            kit = native.u32(0x80004704)
            track = 2 if not stereo else 0
            native.write(kit + track * 0x450 + 0xD6, b"\0")
            before = native.read(kit, 16 * 0x450)
            for bad_slot, bad_track, bad_kit in (
                (300, 16, kit),
                (128, track, kit),
                (300, track, kit + 4),
                (301, track, kit),
            ):
                require(
                    native.call(assign, [bad_slot, bad_track, bad_kit]) == 0xFFFFFFFF,
                    "Invalid assignment accepted",
                )
                require(
                    native.read(kit, len(before)) == before,
                    "Rejected assignment mutated kit",
                )
            require(
                native.call(assign, [300, track, kit]) == 0, "Native assignment failed"
            )
            after = bytearray(before)
            struct.pack_into(">H", after, track * 0x450 + 0x80, 300)
            require(
                native.read(kit, len(before)) == after,
                "Assignment changed other track controls",
            )
            saved_ref = native.alloc(b"\xcc" * 16)
            saved_path = native.alloc(b"/FLEX-SAVED\0")
            require(
                native.call(saver, [node, saved_path, saved_ref], limit=100000000) == 0,
                "Native permanent save failed",
            )
            durable_ref = native.read(saved_ref, 16)
            require(
                durable_ref != native.read(node + 4, 16), "Temporary reference retained"
            )
            require(
                native.read(data_address, result) == expected,
                "Saving changed temporary PCM",
            )
            # Existing files cannot be overwritten, even by a second save call.
            native.write(saved_ref, b"\xcc" * 16)
            require(
                native.call(saver, [node, saved_path, saved_ref]) == 0xFFFFFFFF,
                "Exclusive creation overwrote an existing file",
            )
            require(
                native.read(saved_ref, 16) == b"\xcc" * 16,
                "Failed save published reference",
            )
            failed_path = native.alloc(b"/FLEX-FAILED\0")
            native._hle(0x4015838E, lambda arg: 0)
            require(
                native.call(saver, [node, failed_path, saved_ref]) == 0xFFFFFFFF,
                "Short write accepted",
            )
            native.uc.hook_del(native.service_hooks.pop(0x4015838E))
            require(
                native.read(saved_ref, 16) == b"\xcc" * 16,
                "Short write published reference",
            )
            project = native.call(check.PROJECT_GET, [])
            settings_ptr = native.call(check.SETTINGS_GET, [project])
            settings_data = native.call(
                native.u32(native.u32(settings_ptr) + 0x28), [settings_ptr]
            )
            pool = settings_data + 0x1D2
            require(
                native.read(pool + 300 * 16, 16) == native.read(node + 4, 16),
                "Assignment did not register project reference",
            )
            if args.managed_sources:
                candidate_slot = next(
                    s
                    for s in range(600, 1024)
                    if s % 128
                    and native.u32(pool + s * 16) == 0xFFFFFFFF
                    and native.u32(check.LOADER_KEYS + s * 16) == 0xFFFFFFFF
                    and native.u32(check.LOADER_LEN + s * 4) == 0
                )
                before_pool = native.read(pool, 1024 * 16)
                before_kit = native.read(kit, 16 * 0x450)
                candidate = native.call(
                    accept, [head, start, frames, int(stereo), candidate_slot]
                )
                require(candidate != 0xFFFFFFFF, "Assignment-failure candidate")
                for offset, value in (
                    (20, candidate),
                    (36, candidate_slot),
                    (16, track),
                    (44, kit + 4),
                ):
                    native.write(head + offset, struct.pack(">I", value))
                # Only the old error-dialog tail is modeled; real assign,
                # candidate invalidation, allocator and slot teardown execute.
                native._hle(patches["error_trampoline"], lambda arg: 0)
                native.call(patches["use_finish"], [0, 0])
                native.uc.hook_del(
                    native.service_hooks.pop(patches["error_trampoline"])
                )
                require(
                    native.u32(candidate + 20) == 0
                    and native.u32(candidate + 56) == 1
                    and native.u32(check.LOADER_LEN + candidate_slot * 4) == 0
                    and native.u32(check.LOADER_KEYS + candidate_slot * 16)
                    == 0xFFFFFFFF,
                    "Assignment failure did not clean candidate source/slot",
                )
                require(
                    native.read(pool, 1024 * 16) == before_pool
                    and native.read(kit, 16 * 0x450) == before_kit,
                    "Assignment failure changed prior project/track",
                )
            # An unloaded slot can still be referenced by the project. The
            # native worker must skip it without changing that reference.
            occupied_ref = entries[0]["ref"]
            saved_slot2 = native.read(pool + 2 * 16, 16)
            require(
                native.u32(check.LOADER_LEN + 2 * 4) == 0,
                "Free-slot negative fixture is not CPU-empty",
            )
            native.write(pool + 2 * 16, occupied_ref)
            expected_empty_slot = next(
                slot
                for slot in range(1, 1024)
                if slot % 128
                and native.u32(pool + slot * 16) == 0xFFFFFFFF
                and native.u32(check.LOADER_KEYS + slot * 16) == 0xFFFFFFFF
                and native.u32(check.LOADER_LEN + slot * 4) == 0
            )
            for offset, value in (
                (16, track),
                (24, start + 1),
                (28, frames),
                (32, int(stereo)),
                (44, kit),
            ):
                native.write(head + offset, struct.pack(">I", value))
            require(
                native.call(patches["use_worker"], [], limit=200000000) == 0,
                "Native worker failed free-slot selection",
            )
            require(
                native.u32(head + 36) == expected_empty_slot
                and native.read(pool + 2 * 16, 16) == occupied_ref,
                "Native worker overwrote an unloaded project sample",
            )
            require(
                native.read(native.u32(head) + 8, 4) != native.read(node + 8, 4),
                "Different same-sized takes have aliased content hashes",
            )
            native.write(pool + 2 * 16, saved_slot2)
            progress = native.alloc(bytes(16))
            original_pool = native.read(pool, 1024 * 16)
            # Fault injection only: force native sample persistence failure.
            # The actual short-write and cleanup path was tested above.
            writer_hits = []
            writer_hook = native.uc.hook_add(
                UC_HOOK_CODE,
                lambda *_, hits=writer_hits: hits.append(True),
                begin=0x40043A38,
                end=0x40043A38,
            )
            native._hle(saver, lambda arg: -1)
            require(
                native.call(0x40043A30, [project, 128, progress], limit=200000000) == 0,
                "Project save did not reject a failed recording write",
            )
            native.uc.hook_del(native.service_hooks.pop(saver))
            native.uc.hook_del(writer_hook)
            require(not writer_hits, "Failed recording save entered the project writer")
            require(
                native.read(pool, 1024 * 16) == original_pool,
                "Failed project save changed sample references",
            )
            require(
                native.call(0x40043A30, [project, 128, progress], limit=800000000) & 255
                == 1,
                "Native project save failed",
            )
            durable_ref = native.read(pool + 300 * 16, 16)
            require(
                durable_ref == native.read(node + 32, 16)
                and native.u32(node + 28) == 1,
                "Durable reference not committed",
            )
            # Explicit Save As after an automatic project save must promote
            # this take's existing durable references, while another accepted
            # take remains temporary until the next project save.
            other_node = native.u32(head)
            require(other_node != node, "Missing second-take fixture")
            other_ref = native.read(other_node + 4, 16)
            native.write(pool + expected_empty_slot * 16, other_ref)
            pool_before_named = native.read(pool, 1024 * 16)
            name = native.alloc(b"FLEX-FINAL\0")
            require(
                native.call(patches["save_named"], [node, pool, name], limit=200000000)
                == 0,
                "Native named save failed",
            )
            named_ref = native.read(node + 32, 16)
            expected_pool = bytearray(pool_before_named)
            expected_pool[300 * 16 : 301 * 16] = named_ref
            require(
                native.read(pool, 1024 * 16) == expected_pool
                and native.u32(other_node + 28) == 0,
                "Named save promoted an unrelated take",
            )
            writes_before_collision = len(native.card.writes)
            require(
                native.call(patches["save_named"], [node, pool, name], limit=200000000)
                == 0xFFFFFFFF
                and native.read(node + 32, 16) == named_ref
                and len(native.card.writes) == writes_before_collision,
                "Named save collision changed the file/reference",
            )
            require(
                native.call(0x40043A30, [project, 128, progress], limit=800000000) & 255
                == 1,
                "Project save after named save failed",
            )
            durable_ref = native.read(pool + 300 * 16, 16)
            require(durable_ref == named_ref, "Project save replaced the chosen name")
            writes_before = len(native.card.writes)
            require(
                native.call(persist, [pool]) == 0
                and len(native.card.writes) == writes_before,
                "Repeated project save duplicated a recording",
            )
            # Recreate an entirely stock CPU, with only the resulting sector
            # overlay retained. No temporary registry, native patches or heap.
            reload = check.Firmware(card, args.snapshot, STOCK_MAIN)
            try:
                reload.card.overlay = dict(native.card.overlay)
                reload.call(0x40154358, [])
                check.check_mount(reload, durable_ref)
                restored_project = reload.call(check.PROJECT_GET, [])
                project_data = reload.call(
                    reload.u32(reload.u32(restored_project) + 0x28), [restored_project]
                )
                storage = reload.call(0x4019E41C, [])
                # A restored CPU snapshot includes project-storage caches.
                # Invalidate them through the original OS API before disk reload.
                reload.call(0x400F4A62, [storage])
                reload.call(0x4012F01E, [reload.call(0x4019D8FE, []), 128])
                reload_progress = reload.alloc(bytes(16))
                require(
                    reload.call(
                        0x400F5050,
                        [storage, 128, project_data, reload_progress],
                        limit=800000000,
                    )
                    & 255
                    == 1,
                    "Saved project did not decode from project storage",
                )
                restored_settings = reload.call(check.SETTINGS_GET, [restored_project])
                restored_settings_data = reload.call(
                    reload.u32(reload.u32(restored_settings) + 0x28),
                    [restored_settings],
                )
                restored_ref = reload.read(
                    restored_settings_data + 0x1D2 + 300 * 16, 16
                )
                write_json(
                    folder / "storage-io.json",
                    dict(writes=native.card.writes, reads=reload.card.reads),
                )
                require(
                    restored_ref == durable_ref,
                    "Project reload lost durable sample reference",
                )
                kit_arg = reload.call(check.SETTINGS_KIT_ARG, [restored_settings])
                restored_kit = restored_project + check.PROJECT_KIT
                restored_tracks = reload.call(
                    reload.u32(reload.u32(restored_kit) + check.KIT_DATA_VFUNC),
                    [restored_kit, kit_arg],
                )
                require(
                    reload.s16(
                        restored_tracks + track * check.TRACK_STRIDE + check.TRACK_SLOT
                    )
                    == 300,
                    "Project reload lost track assignment",
                )
                recovered = check.check_load(reload, restored_ref, 300)
                require(
                    recovered["load_d0"] == 0
                    and all(check.sent_pcm_matches(recovered, expected)),
                    "Fresh stock CPU could not recover saved PCM",
                )
                path = reload.alloc(bytes(256))
                path_ptr = reload.call(
                    check.PATH_OF_ID, [int.from_bytes(restored_ref[:4], "big"), 0, path]
                )
                require(
                    path_ptr != 0
                    and reload.read(path_ptr, 256).split(b"\0")[0]
                    == b"/recorded/FLEX-FINAL",
                    "Named path lost after project reload",
                )
            finally:
                reload.close()
            report["cases"].append(
                dict(
                    stereo=stereo,
                    native_bytes=result,
                    native_sha256=hashlib.sha256(expected).hexdigest(),
                    requests=requests,
                    storage_reads=0,
                    storage_writes=0,
                    patches=patches,
                    native_assignment_track=track + 1,
                    only_slot_field_changed=True,
                    failed_load_resource_rollback=True,
                    transactional_assignment_failure_cleanup=args.managed_sources,
                    loader_error_reason_preserved=True,
                    native_file_save_and_fresh_stock_reload=True,
                    explicit_named_save_and_project_reload=True,
                    named_save_only_promotes_selected_take=True,
                    project_pool_references_promoted=True,
                    original_project_save_and_stock_reload=True,
                    project_failure_blocks_original_writer=True,
                    restored_track_assignment=True,
                    unloaded_project_slot_preserved=True,
                    same_size_different_take_hashes_distinct=True,
                    repeated_save_no_sample_writes=True,
                    existing_file_preserved=True,
                    short_write_rejected=True,
                    permanent_save_sector_writes=len(native.card.writes),
                    stock_fallback_pages_equal=True,
                    loader_result={
                        key: loaded[key]
                        for key in (
                            "load_d0",
                            "data_pages",
                            "slot_headers",
                            "events",
                            "len",
                            "rate",
                            "stereo",
                        )
                    },
                )
            )
        finally:
            native.close()
            stock.close()
    report["status"] = "passed"
except Exception as error:
    report["status"] = "failed"
    report["error"] = str(error)
    if "native" in globals():
        sp = native.uc.reg_read(k.UC_M68K_REG_A7)
        report["failure_cpu"] = dict(
            pc=native.uc.reg_read(k.UC_M68K_REG_PC),
            sp=sp,
            stack=struct.unpack(">32I", native.read(sp, 128)),
        )
    raise
finally:
    write_json(out / "report.json", report)
print(out / "report.json")
