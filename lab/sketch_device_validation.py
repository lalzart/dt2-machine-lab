"""Prepared coupled validation of sealed Sketch device bytes; no target changes.

The separate native reset test establishes loading. Here a prepared stock CPU
receives the same initialized segments and hooks, then runs native jobs. Python
supplies the existing recorder/transport models and read-only observations.
"""

import hashlib
import json
import struct
from pathlib import Path

from lab.cpu_extension import GUARD, Segment, segment_chain
from lab.dt2_116 import BASE
from lab.project import ROOT, require, sha256
from lab.sketch_device import ARENAS, END, START, build, relocate


def address(value):
    # Exported END constants are boundaries rather than dereferenceable words.
    for arena in ARENAS:
        if value == arena.source + arena.size:
            return arena.destination + arena.size
    return relocate(value)


class AddressView:
    """Read-only observation symbols; emitter globals and bytes stay unchanged."""

    def __init__(self, module):
        self.module = module

    def __getattr__(self, name):
        value = getattr(self.module, name)
        return address(value) if type(value) is int else value


def read_segments(image, meta):
    start = meta["chain_address"] - BASE
    require(0 <= start < len(image), "Invalid chain source")
    cursor, result = start, []
    for info in meta["segments"]:
        require(cursor + 12 <= len(image), "Truncated segment header")
        size, destination, bss = struct.unpack_from(">III", image, cursor)
        require(
            (size, destination, bss)
            == (info["data_bytes"], info["destination"], info["bss"]),
            "Segment metadata mismatch",
        )
        cursor += 12
        require(cursor + size <= len(image), "Truncated segment data")
        data = image[cursor : cursor + size]
        require(
            hashlib.sha256(data).hexdigest() == info["sha256"], "Segment data changed"
        )
        result.append(Segment(destination, data, bss))
        cursor += size
    require(meta["reservation"] == [START, END], "Unknown device reservation")
    require(
        image[start:] == segment_chain(result, reservation=(START, END)),
        "Invalid segment chain",
    )
    return tuple(result)


class DeviceBuild:
    def __init__(self, folder, stock):
        self.folder = Path(folder).resolve()
        manifest = self.folder / "manifest.json"
        self.manifest = json.loads(manifest.read_text())
        require(
            self.manifest["status"] == "local-build-complete", "Incomplete device build"
        )
        self.image = (self.folder / self.manifest["cpu"]["path"]).read_bytes()
        self.meta = json.loads((self.folder / "native-patches.json").read_text())
        require(
            self.meta == {k: v for k, v in self.manifest["cpu"].items() if k != "path"},
            "Device metadata changed",
        )
        require(
            hashlib.sha256(self.image).hexdigest() == self.meta["sha256"],
            "Device MAIN changed",
        )
        # New validation helpers may be added. Existing emitters, DSP, inputs,
        # contracts and dependencies must still match the accepted build.
        changed = [
            name
            for name, digest in self.manifest["source_hashes"].items()
            if sha256(ROOT / name) != digest
        ]
        require(
            set(changed) <= {"scripts/check-sketch-dsp.py"},
            "Device source drift: " + str(changed),
        )
        require(
            build(
                stock,
                copy_shortcuts=self.meta.get("copy_shortcuts", False),
                stopped_recording=self.meta.get("stopped_recording", False),
                recording_led=self.meta.get("recording_led", False),
                arm_diagnostics=self.meta.get("arm_diagnostics", False),
                clock_fix=self.meta.get("clock_fix", False),
                operation_diagnostics=self.meta.get("operation_diagnostics", False),
                buf_selector=self.meta.get("buf_selector", False),
                performance_controls=self.meta.get("performance_controls", False),
                navigation_fixes=self.meta.get("navigation_fixes", False),
                fixed_buf_slots=self.meta.get("fixed_buf_slots", False),
                startup_capture=self.meta.get("startup_capture", False),
            )
            == (self.image, self.meta),
            "Current emitters differ from sealed device build",
        )
        self.segments = read_segments(self.image, self.meta)
        self.blob_path = self.folder / self.manifest["dsp"]["path"]
        require(
            sha256(self.blob_path) == self.manifest["dsp"]["blob_sha256"],
            "Device DSP changed",
        )
        self.blob = self.blob_path.read_bytes()
        self.identity = dict(
            folder=str(self.folder),
            manifest_sha256=sha256(manifest),
            main_sha256=self.meta["sha256"],
            dsp_sha256=sha256(self.blob_path),
            reservation=self.meta["reservation"],
            validation_source_changes=changed,
            scope="Exact sealed binaries in a prepared CPU/DSP fixture; no paired cold-start claim",
        )

    def install(self, fw):
        for segment in self.segments:
            for at in range(
                segment.destination & ~4095, (segment.end + 4095) & ~4095, 4096
            ):
                fw.m.ensure(at)
            fw.write(segment.destination, segment.data + bytes(segment.bss))
        for hook in self.meta["hooks"]:
            at, before, after = (
                hook["address"],
                bytes.fromhex(hook["before"]),
                bytes.fromhex(hook["after"]),
            )
            require(
                fw.read(at, len(before)) == before,
                "Device hook drift: " + hook["label"],
            )
            fw.write(at, after)
            fw.uc.ctl_remove_cache(at, at + len(after))
        fw.uc.ctl_remove_cache(START, END)
        self.check(fw)

    def check(self, fw):
        for at, size in self.meta["guards"]:
            require(fw.read(at, size) == GUARD, f"Device canary changed at {at:#x}")
        for item in self.meta["writes"] + self.meta["hooks"]:
            if item["kind"] in ("code", "stock-trampoline") or (
                item["kind"] == "pointers" and item["label"].startswith("buf-selector/")
            ):
                raw = bytes.fromhex(item["after"])
                require(
                    fw.read(item["address"], len(raw)) == raw,
                    "Device code changed: " + item["label"],
                )


def adapter(device):
    # Runtime paths must be selected by the caller before these imports.
    from unicorn import (
        UC_HOOK_CODE,
        UC_HOOK_MEM_FETCH,
        UC_HOOK_MEM_READ,
        UC_HOOK_MEM_WRITE,
    )
    from unicorn import m68k_const as k

    from lab import buf_next_bar as original_nb
    from lab import recorder_freeze_worker_code as original_q
    from lab import recorder_worker_code as original_w
    from lab.flex_native_input import NativeFlexInput
    from lab.flex_ui import FlexUI

    nb, q, w = map(AddressView, (original_nb, original_q, original_w))

    class DeviceUI(FlexUI):
        def __init__(self, *args, peer, **kwargs):
            self.peer = peer
            self.next_bar_trace, self.freeze_contexts, self.legacy_accesses = [], [], []
            self.resource_hle_calls = 0
            self.finish_pc = -1
            self.lock_depth = 0
            super().__init__(*args, **kwargs)

        def install(self, main):
            require(
                hashlib.sha256(main).hexdigest() == device.meta["stock_sha256"],
                "Prepared source is not authenticated stock",
            )
            fw = self.fw
            device.install(fw)
            self.recorder_settings = None
            self.native_mode = True
            # No legacy installer or host source/slot/commit callbacks run.
            link = self.clock_state["events"]["dspi2"]
            self.peer.inner, link.peer = link.peer, self.peer

            def legacy(uc, access, at, size, value, *_):
                item = dict(
                    pc=uc.reg_read(k.UC_M68K_REG_PC),
                    access=access,
                    address=at,
                    size=size,
                )
                self.legacy_accesses.append(item)
                raise AssertionError("Device accessed old emulator arena: " + str(item))

            self.hooks.append(
                fw.uc.hook_add(
                    UC_HOOK_MEM_READ | UC_HOOK_MEM_WRITE | UC_HOOK_MEM_FETCH,
                    legacy,
                    begin=0x10300000,
                    end=0x11203FFF,
                )
            )
            for pc in (
                original_nb.START,
                original_nb.STOP,
                original_nb.DISCARD,
                0x400161FE,
                0x400CD6CE,
                0x400124A0,
                0x40001608,
                0x4000172A,
            ):
                self.hooks.append(
                    fw.uc.hook_add(UC_HOOK_CODE, self.hook, begin=pc, end=pc)
                )
            page = address(original_w.TRAMP + 96)
            self.hooks.append(
                fw.uc.hook_add(UC_HOOK_CODE, self.published_page, begin=page, end=page)
            )

            def observe(uc, pc, *_):
                require(not fw.direct, "Host direct device operation")
                sp = uc.reg_read(k.UC_M68K_REG_A7)
                self.next_bar_trace.append(
                    dict(
                        pc=pc,
                        caller=fw.u32(sp),
                        tick=self.tick(),
                        frame=self.peer.calls,
                        phase=fw.u32(nb.STATE + nb.PHASE),
                        count=fw.u32(w.STATE + 80),
                    )
                )

            for pc in (
                nb.ARM,
                nb.START,
                nb.STOP,
                nb.DISCARD,
                nb.QUEUE,
                nb.WORKER,
                nb.DONE,
                nb.CANCEL_FN,
                0x400161FE,
            ):
                self.hooks.append(
                    fw.uc.hook_add(UC_HOOK_CODE, observe, begin=pc, end=pc)
                )

            def receipt(uc, _access, at, size, value, *_):
                pc = uc.reg_read(k.UC_M68K_REG_PC)
                require(size == 4, "Device receipt width")
                if at == nb.STATE + nb.SERIAL:
                    require(
                        nb.IRQ <= pc < nb.IRQ + len(original_nb.irq()),
                        "Non-native bar writer",
                    )
                    self.next_bar_trace.append(
                        dict(
                            event="bar",
                            pc=pc,
                            serial=value,
                            tick=self.tick(),
                            frame=self.peer.calls,
                        )
                    )
                else:
                    self.next_bar_trace.append(
                        dict(event="publish", pc=pc, tick=value, frame=self.peer.calls)
                    )

            for at in (nb.STATE + nb.SERIAL, nb.STATE + nb.PUBLISH_TICK):
                self.hooks.append(
                    fw.uc.hook_add(UC_HOOK_MEM_WRITE, receipt, begin=at, end=at + 3)
                )

            def freeze(uc, pc, *_):
                self.freeze_contexts.append(
                    dict(
                        pc=pc,
                        sr=uc.reg_read(k.UC_M68K_REG_SR),
                        task=fw.u32(q.CURRENT_TCB),
                        direct=fw.direct,
                        phase=fw.u32(q.STATE + 8),
                        tick=self.tick(),
                    )
                )

            for pc in (q.WORKER, q.BODY, q.DONE, w.WORKER):
                self.hooks.append(
                    fw.uc.hook_add(UC_HOOK_CODE, freeze, begin=pc, end=pc)
                )

        def hook(self, uc, pc, size, data):
            if pc == nb.START:
                self.input.ticks_per_frame = 1 if self.fw.u32(nb.STATE + nb.OWN) else 2
            NativeFlexInput.observe(self, uc, pc, size, data)

        def published_page(self, uc, _pc, size, data):
            before = len(self.pages)
            NativeFlexInput.observe(self, uc, 0x400CD638, size, data)
            self.peer.publish(self.pages[before:])

        def process(self):
            raise AssertionError("Device validation attempted a host BUF transaction")

    return DeviceUI
