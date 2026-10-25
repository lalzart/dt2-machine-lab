#!/usr/bin/env python3
# ruff: noqa: E402
"""Isolated OS1.16 CPU-source retirement / DSP double-buffer experiment.

Runs stock CPU loader/heap/filesystem and stock SHARC LP0/ONESHOT instructions.
Recorder, card, locks, wire delivery and optional readback are host models.
No normal builder, dependency, physical device or firmware container is changed.
"""

import argparse
import array
import hashlib
import math
import os
import shutil
import struct
import sys
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lab.project import (
    doctor,
    git,
    require,
    settings,
    sha256,
    source_hashes,
    write_json,
)


def main():
    config = settings()
    if Path(sys.executable).resolve() != config["python"].resolve():
        os.execv(
            str(config["python"]), [str(config["python"]), __file__, *sys.argv[1:]]
        )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--snapshot",
        type=Path,
        default=ROOT.parent
        / "Digitect firmware research project/work/digikit/snapshots/dt2-1.16/running.snap",
    )
    args = parser.parse_args()
    preflight = doctor()
    require(
        sha256(args.snapshot)
        == "175982f14b371fafe0eb54f2943167a94f71370327e65c7fe9941b1336bbc301",
        "Unknown CPU snapshot",
    )
    out = args.output.resolve()
    require(out.is_relative_to(ROOT / "out/runs"), "Use ignored out/runs")
    out.mkdir(parents=True, exist_ok=False)
    os.environ["DT2_LAB_RUN_DIR"] = str(out.relative_to(ROOT / "out/runs"))

    from lab.runtime import LIB, PACK, STOCK_BLOB, STOCK_MAIN  # isort: skip

    import plusdrive_check as check
    import tools.plusdrive as pd
    from unicorn import UC_HOOK_CODE
    from unicorn import m68k_const as registers

    from lab.flex_dsp_probe import DoubleBuffer, control
    from lab.flex_heap import HeapTrace, inspect_heap
    from lab.flex_lite import FlexDsp, RamFirmware
    from lab.flex_native import RESOURCE_SITES
    from lab.flex_native_build import BASE, patch_cpu

    sources = source_hashes()
    for name in sources:
        dest = out / "frozen-sources" / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, dest)
    write_json(out / "source-manifest.json", sources)
    report = dict(
        status="running",
        preflight=preflight,
        firmware="Digitakt II OS 1.16",
        head=git(ROOT, "rev-parse", "HEAD"),
        branch=git(ROOT, "branch", "--show-current"),
        initial_git_status=git(ROOT, "status", "--porcelain=v1"),
        inputs={
            str(p): sha256(p)
            for p in (STOCK_MAIN, STOCK_BLOB, PACK, LIB, args.snapshot)
        },
        scope=__doc__,
        frames_per_take=96000,
        channels=2,
        source_manifest_sha256=sha256(out / "source-manifest.json"),
        readback_on_target=False,
        physical_timing=False,
    )
    firmware = []

    class Observed(RamFirmware):
        def _hle(self, address, fn):
            # Replacing a host seam must remove the earlier hook.
            if not hasattr(self, "hooks"):
                self.hooks = {}
            if address in self.hooks:
                self.uc.hook_del(self.hooks.pop(address))

            def invoke(uc, pc, size, data):
                sp = uc.reg_read(registers.UC_M68K_REG_A7)
                result = fn(lambda index: self.u32(sp + 4 + 4 * index))
                uc.reg_write(registers.UC_M68K_REG_D0, (result or 0) & 0xFFFFFFFF)
                uc.reg_write(registers.UC_M68K_REG_A7, sp + 4)
                uc.reg_write(registers.UC_M68K_REG_PC, self.u32(sp))

            self.hooks[address] = self.uc.hook_add(
                UC_HOOK_CODE, invoke, begin=address, end=address
            )

    def pcm(generation):
        # Integer arithmetic; deterministic across libm implementations.
        return b"".join(
            struct.pack(
                ">hh",
                ((i * (173 + generation * 12)) % 24001) - 12000,
                ((i * (251 + generation * 14)) % 18001) - 9000,
            )
            for i in range(96000)
        )

    payloads = [pcm(1), pcm(2)]
    samples = out / "samples"
    samples.mkdir()
    for index, payload in enumerate(payloads):
        with wave.open(str(samples / f"{index}.wav"), "wb") as stream:
            stream.setparams((2, 2, 48000, 0, "NONE", "not compressed"))
            stream.writeframes(
                b"".join(payload[i : i + 2][::-1] for i in range(0, len(payload), 2))
            )
    card = out / "card.img"
    entries = pd.build(str(samples), str(card), main_os=STOCK_MAIN.read_bytes())

    def new_cpu(overlay=None):
        fw = Observed(card, args.snapshot)
        firmware.append(fw)
        if overlay is not None:
            fw.card.overlay.update(overlay)
        fw.call(0x40154358, [])
        check.check_mount(fw, entries[0]["ref"])
        return fw

    def audio(dsp, wire, slot, count, trigger=False):
        values = array.array("f")
        for index in range(count):
            values.extend(
                dsp.frame(control(wire, slot, trigger=trigger and index == 0))
            )
        require(all(map(math.isfinite, values)), "Nonfinite voice PCM")
        return values.tobytes()

    def refused(fn):
        try:
            fn()
        except ValueError:
            return True
        raise ValueError("Negative control unexpectedly accepted")

    try:
        native, normal = new_cpu(), new_cpu()
        image, metadata = patch_cpu(STOCK_MAIN.read_bytes(), managed_sources=True)
        for patch in metadata["writes"]:
            address = patch["address"]
            require(
                native.read(address, len(bytes.fromhex(patch["before"])))
                == bytes.fromhex(patch["before"]),
                "Native overlay guard",
            )
            native.write(address, bytes.fromhex(patch["after"]))
        native.uc.ctl_remove_cache(BASE, BASE + len(image))
        loc = metadata["locations"]
        write_json(out / "native-overlay.json", metadata)
        active_payload = [payloads[0]]

        def service(arg):
            command, mono, first, count = struct.unpack(
                ">HHII", native.read(arg(1), 12)
            )
            require(
                arg(0) == 12 and arg(2) == 2048 and command == 4 and mono == 0,
                "Unexpected recorder service",
            )
            native.write(
                0x4FE79340,
                active_payload[0][first * 4 : (first + count) * 4].ljust(2048, b"\0"),
            )
            return 0

        native._hle(0x400124A0, service)
        heap = HeapTrace(native)
        allocations, nodes, natives, publications = [], [], [], []
        reference_pages = []
        report["native_takes"] = []
        for index, slot in enumerate((300, 301)):
            active_payload[0] = payloads[index]
            native.pages.clear()
            heap.phase = f"accept-{index}"
            started = time.perf_counter()
            node = native.call(
                loc["accept"], [loc["state"], 0, 96000, 1, slot], limit=200_000_000
            )
            require(node != 0xFFFFFFFF, "Native accept failed")
            source, length = native.u32(node + 20), native.u32(node + 12)
            original = native.read(source, length)
            require(original[64:-16] == payloads[index], "Native recorder copy differs")
            allocation = native.slot(slot)
            require(
                allocation["start"] + allocation["size"] <= 0x18800400,
                "Probe enters Capicola reservation",
            )
            allocations.append(allocation)
            nodes.append(node)
            natives.append(original)
            publications.append(list(native.pages))
            reference = check.check_load(normal, entries[index]["ref"], slot)
            require(reference["load_d0"] == 0, "Stock reference load failed")
            reference_pages.append(list(normal.pages))
            # No backing exists: the actual retirement guard must retain RAM.
            require(
                native.call(loc["retire_source"], [node]) == 1
                and native.u32(node + 20) == source,
                "Unsaved source retired by normal code",
            )
            before = inspect_heap(native.read)
            # Deliberate isolated unsafe A control: detach source and execute stock
            # free, without introducing that behavior into any normal build.
            heap.phase = f"forced-unsaved-release-{index}"
            native.write(source, b"\xa5" * length)
            native.write(node + 20, bytes(4))
            native.call(0x4011E8FC, [source])
            after = inspect_heap(native.read)
            require(
                after.free_bytes - before.free_bytes == 524288,
                "Unexpected source block size",
            )
            report["native_takes"].append(
                dict(
                    slot=slot,
                    node=hex(node),
                    source=hex(source),
                    file_bytes=length,
                    source_block_released=after.free_bytes - before.free_bytes,
                    allocation=allocation,
                    packets=len(publications[-1]),
                    accept_and_control_host_seconds=time.perf_counter() - started,
                )
            )
        print("Native A/B publication and source-free controls passed", flush=True)
        wire = normal.capture_assignment(300)
        reference_dsp, dsp = FlexDsp(), FlexDsp()
        before = dsp.core.stats()["instructions"]
        started = time.perf_counter()
        dsp.publish(publications[0])
        report["publication_a"] = dict(
            instructions=dsp.core.stats()["instructions"] - before,
            host_seconds=time.perf_counter() - started,
        )
        left, right, lane_bytes, _, _ = dsp.slot_record(300)
        for relative in (left, right):
            require(
                dsp.sample_bytes(relative, 10)
                == dsp.sample_bytes(relative + lane_bytes, 10),
                "Stock interpolation guard differs",
            )
        report["publication_a"]["ten_byte_tail_guards_equal_head"] = True
        reference_dsp.publish(reference_pages[0])
        expected = audio(reference_dsp, wire, 300, 48, True)
        actual = audio(dsp, wire, 300, 48, True)
        require(
            expected == actual
            and max(map(abs, struct.unpack(f"<{len(actual) // 4}f", actual))) > 0,
            "Freed-source playback differs from ordinary loading",
        )
        require(dsp.reading(300), "A is not active")
        report["released_source_voice_parity"] = dict(
            exact=True, blocks=48, pcm_sha256=hashlib.sha256(actual).hexdigest()
        )
        (out / "voice-a.f32").write_bytes(actual)

        pool = DoubleBuffer([allocations[0]["size"], allocations[1]["size"]])
        a = pool.begin(0, allocations[0]["size"] // 4096)
        for index in range(pool.buffers[0].expected):
            pool.page(a, index)
        pool.commit(a)
        pool.select(a)
        pool.pin(a)
        b = pool.begin(1, allocations[1]["size"] // 4096)
        negatives = dict(
            incomplete=refused(lambda: pool.commit(b)),
            premature_reuse=refused(lambda: pool.begin(0, 1)),
            exhaustion=refused(lambda: DoubleBuffer([4096]).begin(0, 2)),
        )
        # B transfers interleave with stock audio blocks. A has an independent
        # address and reader. Actual peripheral DMA/interrupt concurrency is modeled.
        data_index = 0
        before = dsp.core.stats()["instructions"]
        expected_tail, actual_tail = [], []
        for packet in publications[1]:
            dsp.publish([packet])
            if packet[0] != 0xFFFFFFFF:
                pool.page(b, data_index)
                data_index += 1
            expected_tail.append(audio(reference_dsp, wire, 300, 1))
            actual_tail.append(audio(dsp, wire, 300, 1))
        require(
            expected_tail == actual_tail and dsp.reading(300), "Preparing B disturbed A"
        )
        report["interleaved_b"] = dict(
            blocks=len(actual_tail),
            a_exact=True,
            instructions_including_audio=dsp.core.stats()["instructions"] - before,
        )
        pool.commit(b)
        pool.select(b)
        negatives["old_reader_after_swap"] = refused(lambda: pool.retire(a))
        pointer_a = dsp.voice()["pointer"]
        audio(dsp, wire, 301, 8)
        require(
            dsp.voice()["pointer"] == pointer_a and dsp.reading(300),
            "Selection unexpectedly replaced active A",
        )
        audio(dsp, wire, 301, 8, True)
        require(
            dsp.reading(301) and not dsp.reading(300), "B retrigger did not acquire B"
        )
        # Only these two exercised lanes are released here. The host helper scans
        # all 32; it is not an audited target reader-retirement implementation.
        pool.unpin(a)
        pool.retire(a)
        replacement = pool.begin(0, 1)
        negatives["stale_handle"] = refused(lambda: pool.pin(a))
        pool.project_change()
        negatives["project_change"] = refused(lambda: pool.commit(replacement))
        report["double_buffer"] = dict(
            selection_preserves_active_pointer=True,
            retrigger_acquires_b=True,
            distinct_allocations=allocations[0]["start"] != allocations[1]["start"],
            negatives=negatives,
            identity_count=native.u32(loc["state"] + 4),
            identities_recycled=0,
        )
        print("Stock voice parity and A-playing/B-preparing swap passed", flush=True)

        partial = FlexDsp()
        partial.publish(publications[0][:-1])
        require(
            partial.slot_record(300)[2] == 0, "Missing final header published length"
        )
        require(
            not any(audio(partial, wire, 300, 8, True)),
            "Incomplete allocation became audible",
        )
        mutated = FlexDsp(dsp.state_bytes())
        first_page = (allocations[1]["start"] - 0x400) // 4096
        mutated.publish([(first_page, bytes(4096), 0)])
        require(
            audio(mutated, wire, 301, 8) != audio(dsp, wire, 301, 8),
            "Unsafe overwrite negative did not change audio",
        )
        report["native_publication_controls"] = dict(
            missing_header_silent=True,
            active_page_overwrite_changes_audio=True,
            scope="Sequential emulator calls; no claim about hardware cache or interrupt races",
        )

        # No native DSP -> CPU source provider exists in this candidate.
        dest, handle = native.alloc(b"\xcc" * 128), native.alloc(16)
        native.call(RESOURCE_SITES["open"][0], [nodes[0] + 4, handle])
        result = native.call(RESOURCE_SITES["read"][0], [dest, 128, handle])
        require(
            result == 0xFFFFFFFF and native.read(dest, 128) == b"\xcc" * 128,
            "Missing backing read did not fail closed",
        )
        native.call(RESOURCE_SITES["close"][0], [handle])
        failed_ref = native.alloc(b"\xcc" * 16)
        path = native.alloc(b"/recorded/NO-READBACK\0")
        native.call(0x40157192, [loc["directory"]])
        heap.phase = "missing-readback-controls"
        writes = len(native.card.writes)
        require(
            native.call(loc["save"], [nodes[0], path, failed_ref], limit=50_000_000)
            == 0xFFFFFFFF,
            "Unsaved retired source unexpectedly saved",
        )
        require(
            len(native.card.writes) == writes
            and native.read(failed_ref, 16) == b"\xcc" * 16,
            "Missing readback wrote storage",
        )
        report["without_readback"] = dict(
            resource_read_failed=True, save_failed=True, storage_writes=0
        )
        project_pool = native.alloc(b"\xff" * 16384)
        native.write(project_pool + 16, native.read(nodes[0] + 4, 16))
        old_pool = native.read(project_pool, 16384)
        require(
            native.call(loc["persist"], [project_pool], limit=100_000_000) == 0xFFFFFFFF
            and native.read(project_pool, 16384) == old_pool,
            "Source-less project save did not fail closed",
        )
        report["without_readback"][
            "project_persistence_failed_without_reference_commit"
        ] = True

        # Host peek models the MISSING reverse transport, not shared pointers.
        # Retain 80 bytes of immutable file metadata; reconstruct PCM from SHARC.
        maximum = [0]
        calls = []
        node_slots = dict(zip(nodes, (300, 301), strict=True))
        metadata_bytes = {
            node: (data[:64], data[-16:])
            for node, data in zip(nodes, natives, strict=True)
        }

        def dsp_readback(arg):
            node, destination, count, position = [arg(i) for i in range(4)]
            require(
                node in node_slots and 0 <= count <= 32768, "Readback request bounds"
            )
            slot = node_slots[node]
            left, right, lane_bytes, rate, stereo = dsp.slot_record(slot)
            require(
                (lane_bytes, rate, stereo) == (192000, 48000, 1),
                "Readback identity/extent",
            )
            count = min(count, native.u32(node + 12) - position)
            header, footer = metadata_bytes[node]
            result = bytearray()
            # Intentionally byte-indexed to cover arbitrary resource offsets.
            for offset in range(position, position + count):
                if offset < 64:
                    result.append(header[offset])
                elif offset < 384064:
                    frame, byte = divmod(offset - 64, 4)
                    base = left if byte < 2 else right
                    result.append(
                        dsp.core.peek(0x8422B9C8 + base + frame * 2 + (1 - byte % 2), 1)
                    )
                else:
                    result.append(footer[offset - 384064])
            native.write(destination, result)
            maximum[0] = max(maximum[0], count)
            calls.append(dict(node=hex(node), position=position, count=count))
            return count

        native._hle(loc["read_backing"], dsp_readback)
        report["host_assisted_save"] = dict(
            saved=[],
            max_chunk=0,
            calls=calls,
            transport="host NativeCore.peek; NOT firmware readback",
        )
        saved = []
        for index, node in enumerate(nodes):
            path = native.alloc(f"/recorded/DSP-{index}".encode() + b"\0")
            output_ref = native.alloc(16)
            heap.phase = f"host-assisted-dsp-save-{index}"
            require(
                native.call(loc["save"], [node, path, output_ref], limit=200_000_000)
                == 0,
                "Host-assisted DSP save failed",
            )
            reload = new_cpu(native.card.overlay)
            loaded = check.check_load(reload, native.read(output_ref, 16), 310 + index)
            require(loaded["load_d0"] == 0, "Saved sample reload failed")
            require(
                all(check.sent_pcm_matches(loaded, natives[index])),
                "Readback save PCM differs",
            )
            saved.append(
                dict(
                    slot=310 + index,
                    exact_pcm=True,
                    reference=native.read(output_ref, 16).hex(),
                )
            )
        print(
            "Both host-assisted DSP saves and independent stock reloads passed",
            flush=True,
        )
        report["host_assisted_save"] = dict(
            saved=saved,
            max_chunk=maximum[0],
            calls=calls,
            transport="host NativeCore.peek; NOT firmware readback",
        )

        # B: host source adapter supplies chunks directly to the original loader.
        # No long-lived PCM allocation is made in guest CPU heap. The fixture
        # remains host-owned; this is not a continuous real recorder producer.
        stream = new_cpu()
        stream.enable_ram()
        streaming_heap = HeapTrace(stream)
        ref = stream.source(payloads[0], True, max_frames=96000)
        loaded, packets = stream.load(ref, 320)
        require(
            all(check.sent_pcm_matches(loaded, natives[0])), "Chunked loader differs"
        )
        report["bounded_source_adapter"] = dict(
            heap=streaming_heap.report(),
            largest_resource_read=max(
                e[3] for e in stream.source_events if e[0] == "read"
            ),
            pcm_equal=True,
            guest_cpu_pcm_retained=False,
            producer="host RAM source shim; not a native capture implementation",
        )
        report["heap"] = heap.report()
        report["dsp_bytes_two_takes"] = sum(a["size"] for a in allocations)
        report["dsp_a_packet_wire_bytes"] = len(publications[0]) * 4100
        report["native_source_pointers_at_end"] = [
            native.u32(node + 20) for node in nodes
        ]
        require(sources == source_hashes(), "Source drift during experiment")
        report["status"] = "passed"
        write_json(out / "report.json", report)
        print(f"PASS: {out / 'report.json'}", flush=True)
    except BaseException as error:
        report.update(status="failed", error=f"{type(error).__name__}: {error}")
        write_json(out / "report.json", report)
        raise
    finally:
        for fw in firmware:
            fw.close()


if __name__ == "__main__":
    main()
