"""RAM source boundary for an isolated stock OS 1.16 sample loader.

Uses the pinned DigiKit GPL-2.0 tools through imports. No firmware code is
copied or patched. The original loader owns the sample allocation and packing.
This host adapter is not yet an on-device temporary-resource implementation.
"""

import ctypes
import hashlib
import struct

# Runtime installs the pinned tool import paths first.
# isort: off
from lab.project import require
from lab.runtime import STOCK_MAIN

import plusdrive_check as check
import tools.plusdrive as pd
# isort: on

BLOCK_VECTOR = 0x405A0F64
SLOT_BLOCK = 0x405B5368
UNLOAD = 0x401540C6
CLEAR_SLOT = 0x40153BEA


class RamFirmware(check.Firmware):
    def __init__(self, card, snapshot):
        super().__init__(str(card), str(snapshot), str(STOCK_MAIN))
        self.sources = {}
        self.handles = {}
        self.source_events = []
        self.source_hooks = []
        self.assignment_hooks = []

    def source(self, pcm, stereo, generation=1, *, max_frames=20000):
        require(1 <= generation <= 65535, "Generation outside prototype range")
        require(len(pcm) % (4 if stereo else 2) == 0, "Partial PCM frame")
        frames = len(pcm) // (4 if stereo else 2)
        require(141 <= max_frames <= 480000, "Unsupported PCM capacity")
        require(
            141 <= frames <= max_frames, f"PCM outside 141..{max_frames} frame bound"
        )
        native = pd.build_native_sample(pcm, stereo)
        identity = 0x7FFE0000 + generation
        require(identity not in self.sources, "Generation identity reused")
        content = int.from_bytes(hashlib.sha256(native).digest()[:4], "big") | 1
        ref = struct.pack(">4I", identity, content, len(native), generation)
        self.sources[identity] = {"data": native, "ref": ref}
        return ref

    def enable_ram(self):
        """Scope these replacements to a separate RAM-only Firmware instance."""
        require(not self.source_hooks, "RAM source already installed")
        callbacks = {
            check.RESOLVE_REF: self.resolve,
            check.REF_KEY: self.key,
            0x4015B2D0: self.open_source,
            0x4015BA22: self.size,
            0x4015832E: self.read_source,
            check.PATH_OF_ID: self.name,
            0x401585E4: self.close_source,
        }
        for address, fn in callbacks.items():
            self._hle(address, fn)
            self.source_hooks.append(hex(address))

    def get_source(self, identity):
        require(identity in self.sources, f"Unknown temporary identity {identity:#x}")
        return self.sources[identity]

    def resolve(self, arg):
        ref = self.read(arg(0), 16)
        identity = struct.unpack_from(">I", ref)[0]
        source = self.get_source(identity)
        require(ref == source["ref"], "Temporary reference differs")
        self.write(arg(1), struct.pack(">I", identity))
        self.source_events.append(["resolve", identity])
        return 0

    def key(self, arg):
        self.write(arg(1), self.get_source(arg(0))["ref"])
        return 0

    def open_source(self, arg):
        ref = self.read(arg(0), 16)
        identity = struct.unpack_from(">I", ref)[0]
        require(ref == self.get_source(identity)["ref"], "Open key differs")
        handle = arg(1)
        self.write(handle, struct.pack(">I", identity) + bytes(8))
        self.handles[handle] = [identity, 0]
        self.source_events.append(["open", identity])
        return 0

    def size(self, arg):
        return len(self.get_source(arg(0))["data"])

    def read_source(self, arg):
        dest, requested, handle = arg(0), arg(1), arg(2)
        require(handle in self.handles, "Unknown RAM read handle")
        identity, position = self.handles[handle]
        data = self.get_source(identity)["data"]
        count = min(requested, len(data) - position)
        require(0 <= count <= 0x8000, "RAM read extent")
        self.write(dest, data[position : position + count])
        self.handles[handle][1] += count
        self.source_events.append(["read", identity, position, count])
        return count

    def name(self, arg):
        self.get_source(arg(0))
        dest = arg(2)
        self.write(dest, b"/TEMP/FLEX-RAM\0".ljust(32, b"\0"))
        return dest

    def close_source(self, arg):
        handle = arg(0)
        require(handle in self.handles, "Unknown RAM close handle")
        identity, _ = self.handles.pop(handle)
        self.source_events.append(["close", identity])
        return 0

    def slot(self, slot):
        require(0 < slot < 0x400 and slot % 128, "Reserved slot")
        index = self.u32(SLOT_BLOCK + slot * 4)
        key = self.u32(check.LOADER_KEYS + slot * 16)
        empty = key == 0xFFFFFFFF and self.u32(check.LOADER_LEN + slot * 4) == 0
        result = {"slot": slot, "block_index": index, "empty": empty}
        if not empty:
            begin, end = self.u32(BLOCK_VECTOR), self.u32(BLOCK_VECTOR + 4)
            require(end >= begin and (end - begin) % 0x34 == 0, "Block vector extent")
            require(index < (end - begin) // 0x34, "Block index outside vector")
            address = begin + index * 0x34
            start, size = struct.unpack(">II", self.read(address + 0x10, 8))
            require(
                start >= 0x400 and size > 0 and size % 0x2000 == 0,
                "Allocation alignment",
            )
            require(start + size <= 0x19000400, "Sample arena capacity")
            result.update(start=start, size=size, record=address)
        return result

    def free_slot(self):
        for slot in range(1, 0x400):
            if slot % 128 and self.slot(slot)["empty"]:
                return slot
        raise RuntimeError("No unused normal slot")

    def load(self, ref, slot):
        require(
            self.slot(slot)["empty"],
            "Detach and unload the occupied slot before replacement",
        )
        result = check.check_load(self, ref, slot)
        require(result["load_d0"] == 0, f"Sample load failed: {result['load_d0']}")
        result["allocation"] = self.slot(slot)
        return result, list(self.pages)

    def capture_assignment(self, slot):
        """Write live track 1, execute stock refresh and track-frame packing.

        This is a controlled guest-RAM edit, not a panel gesture. The bounded
        handler stops after packing all 16 tracks, before its remaining tail.
        Existing DigiKit settled-smoother calibration is explicit.
        """
        from sharc_capture_run import install_smoother_calibration
        from unicorn import UC_HOOK_CODE
        from unicorn import m68k_const as k

        require(
            slot == 0 or not self.slot(slot)["empty"],
            "Cannot assign unpublished CPU slot",
        )
        live = self.u32(0x80004704)
        require(0x40000000 <= live < 0x4FE00000, "Missing live kit")
        self.write(live + 0x80, struct.pack(">H", slot))
        self.write(live + 0xD6, b"\0")
        self.call(0x4002D438, [live + 0x34, 0])
        if not self.assignment_hooks:

            def at(pc, fn):
                self.assignment_hooks.append(
                    self.uc.hook_add(UC_HOOK_CODE, fn, begin=pc, end=pc)
                )

            install_smoother_calibration(self.m, at, True, ())
        for address in (0x409664F4, 0x409664F0, 0x409664F8, 0x409664EC):
            self.write(address, bytes(4))
        # ISR sends the previous frame first. Skip that send, then inspect
        # the frame it actually constructs from the live track record.
        self.write(0x402A1488, struct.pack(">I", 1))
        self.uc.reg_write(k.UC_M68K_REG_SR, 0x2700)
        self.uc.reg_write(k.UC_M68K_REG_A7, check.STACK_TOP)
        self.uc.emu_start(0x4002DD0C, 0x4002ED0C, count=1_000_000)
        require(
            self.uc.reg_read(k.UC_M68K_REG_PC) == 0x4002ED0C,
            "Track packing did not finish",
        )
        wire = self.read(0x80005348, 0x802)
        require(
            int.from_bytes(wire[0xE0:0xE2], "big") == slot, "Slot did not reach wire"
        )
        require(wire[0x94:0x96] == b"\0\0", "Stock ONESHOT not selected")
        return wire

    def unload(self, slot, dsp):
        require(
            not dsp.reading(slot), "Refuse to unload a sample still read by a voice"
        )
        self.pages.clear()
        self.call(UNLOAD, [slot])
        self.call(CLEAR_SLOT, [slot])
        require(self.slot(slot)["empty"], "CPU slot did not clear")
        pages = list(self.pages)
        dsp.publish(pages)
        require(dsp.slot_record(slot)[2] == 0, "DSP slot did not clear")
        return pages


def publication_bytes(pages):
    """Captured CPU page calls converted to LP0's established byte order."""
    packets = []
    for tag, block, header in pages:
        require(len(block) == 0x1000, "Incomplete publication page")
        width = 4 if header else 2
        payload = b"".join(
            block[i : i + width][::-1] for i in range(0, len(block), width)
        )
        packets.append(struct.pack("<I", tag) + payload)
    return packets


from lab.dsp import Dsp  # noqa: E402


class FlexDsp(Dsp):
    def __init__(self, state=None):
        super().__init__()
        if state is not None:
            require(
                self.core._lib.sharc_native_import_state(
                    self.core._handle, state, len(state)
                )
                == 0,
                "Prepared DSP import failed",
            )

    def state_bytes(self):
        self.core.set_option(self.native.OPT_EXPORT_RANGES, 1)
        capacity = 1 << 20
        while capacity <= 64 << 20:
            buf = ctypes.create_string_buffer(capacity)
            size = self.core._lib.sharc_native_export_state(
                self.core._handle, buf, capacity
            )
            if size >= 0:
                return buf.raw[:size]
            capacity = -size
        raise RuntimeError("Prepared DSP state exceeds 64 MiB")

    def frame(self, wire):
        before = [
            self.core.peek(0x2412CC + v * 0x1D8)
            and self.core.peek(0x2412CC + v * 0x1D8 + 0x1B8, 1)
            for v in (0, 1)
        ]
        block = super().frame(wire)
        after = [
            self.core.peek(0x2412CC + v * 0x1D8)
            and self.core.peek(0x2412CC + v * 0x1D8 + 0x1B8, 1)
            for v in (0, 1)
        ]
        # Inactive or detached voices can retain an old work buffer. The tap
        # emits silence only when the lane has no valid active pointer at both
        # boundaries. Keep the final transition block, including its tail.
        for lane in (0, 1):
            if not before[lane] and not after[lane]:
                block[lane::2] = [0.0] * (len(block) // 2)
        return block

    def publish(self, pages):
        """Original LP0 callback with modeled DMA/interrupt entry and exit."""
        import sharc_trace as st

        core, native = self.core, self.native
        saved = {code: core.get_reg(code) for code in set(st.UREG_CODES.values())}

        def callback(pc, stop, bound):
            core.set_option(native.OPT_STOP_PC, stop)
            core.fresh_call(pc)
            core.run(bound)
            require(
                core.pc() == stop,
                f"LP0 call stopped at {core.pc():#x}: {core.halt_reason}",
            )
            core.set_option(native.OPT_STOP_PC, -1)
            for code, value in saved.items():
                core.set_reg(code, value)

        callback(0x1C7ED7, 0x1C83FF, 128)
        require(
            core.peek(0x268224) == 0x268240 and core.peek(0x26822C) == 0x401,
            "LP0 descriptor differs",
        )
        for packet in publication_bytes(pages):
            require(
                core.poke(0x268240, packet, 1) == len(packet), "LP0 delivery failed"
            )
            core.set_reg(st.UREG_CODES["R4"], st.Const(0))
            core.set_reg(st.UREG_CODES["R8"], st.Const(4))
            core.set_reg(st.UREG_CODES["R12"], st.Const(0x268220))
            callback(0x1C7E1F, 0x1C834A, 20000)

    def sample_bytes(self, relative, count):
        return bytes(self.core.peek(0x8422B9C8 + relative + i, 1) for i in range(count))

    def slot_record(self, slot):
        return [self.core.peek(0x257810 + slot * 0x14 + i * 4) for i in range(4)] + [
            self.core.peek(0x257810 + slot * 0x14 + 16, 1)
        ]

    def reading(self, slot):
        left, right, length, _, _ = self.slot_record(slot)
        if not length:
            return False
        addresses = {0x8422B9C8 + left, 0x8422B9C8 + right}
        return any(
            self.core.peek(0x2412CC + v * 0x1D8) in addresses
            and self.core.peek(0x2412CC + v * 0x1D8 + 0x1B8, 1)
            for v in range(32)
        )

    def voice(self):
        core, base = self.core, 0x2412CC

        def q(offset, signed=False):
            value = core.peek(base + offset) | (core.peek(base + offset + 4) << 32)
            if signed and value & (1 << 63):
                value -= 1 << 64
            return value / 2**31

        return {
            "pointer": core.peek(base),
            "start": q(0x198),
            "end": q(0x1A0),
            "step": q(0x1A8, True),
            "active": core.peek(base + 0x1B8, 1),
            "reverse": core.peek(base + 0x1BB, 1),
            "loop": core.peek(base + 0x1BC, 1),
        }
