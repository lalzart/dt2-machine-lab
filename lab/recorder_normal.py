"""Gate-A adapters: untouched stock recorder and opt-in NORMAL/BUF dispatch.

No FREEZE native implementation is installed here. Recording audio remains an
external peer; NORMAL save/name/assignment use original firmware instructions.
"""

# Runtime paths must be installed before importing the pinned Unicorn module.
# isort: off
from lab.flex_buffer_ui import ARENA, TABLE, BufferUI
from lab.flex_native_input import Memory, NativeFlexInput
from lab.flex_recorder import RecorderInput
from lab.project import require
from lab.recorder_destination import (
    FILTER,
    RESERVED,
    SEARCH_BYTES,
    SEARCH_SITE,
    allocation_filter,
)

# Runtime import paths are installed by the modules above.
from unicorn import UC_HOOK_CODE
from unicorn import m68k_const as k
# isort: on

PEER_SITES = (
    0x40015FDA,
    0x400161FE,
    0x40015FF8,
    0x400CD6CE,
    0x400124A0,
    0x40001608,
    0x4000172A,
    0x400CD638,
)


class StockRecorderPeer:
    """Same recorder input model as native Flex; no firmware patch at all."""

    def __init__(self, gui, clock_state, source, card, main, *, enabled=True):
        self.input = RecorderInput(source)
        self.phase, self.error = "ready", None
        self.current = self.target = self.controller = self.view = None
        self.pages, self.events, self.hooks = [], [], []
        self.lock_depth = 0
        self.finish_pc = -1
        self.fw = None
        original_build = gui.build

        def build(*args, **kwargs):
            result = original_build(*args, **kwargs)
            self.fw = Memory(result[0])
            for pc in PEER_SITES:
                self.hooks.append(
                    self.fw.uc.hook_add(UC_HOOK_CODE, self.observe, begin=pc, end=pc)
                )
            return result

        gui.build = build

    observe = NativeFlexInput.observe
    tick = NativeFlexInput.tick


class NormalBufferUI(BufferUI):
    """Separate experimental adapter; preserves the historical TAKE adapter.

    The only NORMAL code redirections are the preexisting ready-page C cell
    and setter. Original trim YES is neither replaced nor returned from by a
    host callback. Buffer resource orchestration remains the older host model.
    """

    def __init__(self, *args, **kwargs):
        self.lock_depth = 0
        self.finish_pc = -1
        super().__init__(*args, **kwargs)

    def install(self, main):
        require(
            self.fw.read(SEARCH_SITE, 6) == SEARCH_BYTES, "Stock free-slot search drift"
        )
        code = allocation_filter()  # Independent ColdFire audit before patch.
        super().install(main)
        fw = self.fw
        require(fw.u32(TABLE) == ARENA + 0x110, "DEST string table drift")
        fw.write(fw.u32(TABLE), b"NORMAL\0")
        fw.write(0x402296FB, b"Y:SAVE\0")
        fw.write(RESERVED, b"\xff" * (13 * 4))
        fw.write(FILTER, code)
        fw.write(SEARCH_SITE, bytes.fromhex("4ef9") + FILTER.to_bytes(4, "big"))
        fw.uc.ctl_remove_cache(SEARCH_SITE, SEARCH_SITE + 6)
        fw.uc.ctl_remove_cache(FILTER, FILTER + len(code))
        for pc in (0x40001608, 0x4000172A, 0x400CD638):
            self.hooks.append(fw.uc.hook_add(UC_HOOK_CODE, self.hook, begin=pc, end=pc))

    def hook(self, uc, pc, size, data):
        if self.destination == 0:
            # Observes real recursive locks, unlike the older bounded-call
            # adapter which requires fw.direct for command-4 PCM retrieval.
            NativeFlexInput.observe(self, uc, pc, size, data)
            if pc == 0x40022FBE:
                self.record_event("normal-stock-trim-yes")
            elif pc == 0x40023026:
                self.record_event("normal-stock-save-progress")
            return
        if pc in (0x40001608, 0x4000172A, 0x400CD638):
            return
        super().hook(uc, pc, size, data)

    def extra_hook(self, uc, pc, *args):
        if pc == 0x40021DE0:
            self.fw.write(
                0x402296FB, b"Y:SAVE\0" if self.destination == 0 else b"Y:USE \0"
            )
            if self.destination == 0 or not self.setup_done:
                sp = uc.reg_read(k.UC_M68K_REG_A7)
                self.view = self.fw.u32(sp + 4)
                return  # No eager buffer slot/setup side effect in NORMAL.
        super().extra_hook(uc, pc, *args)

    def setup(self):
        import struct

        super().setup()
        # Only previously checked empty fixture slots become reservations.
        # No synthetic placeholders are written into unused project records.
        reserved = self.buffer_slots + self.private_slots + [-1]
        self.fw.write(
            RESERVED, struct.pack(">13I", *(n & 0xFFFFFFFF for n in reserved))
        )
