"""Explicit emulator-only adapter around the native ColdFire UP core.

Native instructions collect/count keys and decide note order/deadlines. Python
places temporary diagnostic memory and services the core between worker chunks.
Stock note APIs execute in bounded borrowed-context transactions. This adapter
is not permanent firmware placement or an on-device scheduler implementation.
"""
import struct

from unicorn import UC_HOOK_CODE, m68k_const as r

from lab import arp_native as native
from lab.arp_emulation import CODE, STATE, STACK, STOP
from lab.emit import Code
from lab.project import require

ON, OFF, KEY = 0x4011FE12, 0x4012020C, 0x4005DC58
TICK = 0x40966500
PRESS_RETURN, RELEASE_RETURN = 0x4005C666, 0x4005C718


def collector(address, function, release=False):
    c = Code()
    c.emit("202f0008")  # resolved pitch in stock argument 2
    if not release:
        c.emit("222f000c 2f01")
    c.emit("2f00"); c.imm("4879", STATE); c.imm("4eb9", function)
    c.emit("4fef0008" if release else "4fef000c")
    if release:
        c.emit("4a80"); c.branch(7, "done")
        # Close an arp gate immediately in the same native UI context.
        c.emit("7000 2f00 48780040")
        c.imm("2039", STATE + native.FIELDS["off"]); c.emit("2f00 7000 2f00")
        c.imm("4eb9", OFF); c.emit("4fef0010")
        c.imm("41f9", STATE); c.emit("7000 21400034")
        c.label("done")
    c.emit("4e75")
    return c.finish(address)


class ArpUI:
    def __init__(self, gui, clock_state, main, enabled=True):
        self.machine = None
        self.direct = False
        self.collecting = False
        self.playing = False
        self.pending_panic = False
        self.enabled = enabled
        self.inputs, self.outputs, self.stock_calls = [], [], []
        self.hooks = []
        self.calls = 0
        self.entries = native.build(CODE)
        self.press_entry, self.release_entry = CODE + 0x1800, CODE + 0x1C00
        old_build, old_spin = gui.build, gui.spin

        def build(*args, **kwargs):
            result = old_build(*args, **kwargs)
            self.machine = result[0]
            self.install(main)
            return result

        def spin(*args, **kwargs):
            result = old_spin(*args, **kwargs)
            self.service()
            return result

        gui.build, gui.spin = build, spin
        self.clock_state = clock_state

    @property
    def uc(self):
        return self.machine.uc

    def u32(self, address):
        return int.from_bytes(self.uc.mem_read(address, 4), "big")

    def tick(self):
        return self.u32(TICK)

    def raw(self):
        return bytes(self.uc.mem_read(STATE, native.SIZE))

    def field(self, name):
        return self.u32(STATE + native.FIELDS[name])

    def install(self, main):
        for address in (ON, OFF, KEY):
            expected = main[address - 0x40000400:address - 0x40000400 + 8]
            require(bytes(self.uc.mem_read(address, 8)) == expected,
                    f"Arp hook bytes changed at {address:#x}")
        require(not any(lo < CODE + 0x10000 and hi >= CODE
                        for lo, hi, _ in self.uc.mem_regions()),
                "Arp diagnostic memory already mapped")
        for address in range(CODE, CODE + 0x10000, 4096):
            self.machine.ensure(address)
        for address, code in self.entries.values():
            self.uc.mem_write(address, code)
        self.uc.mem_write(self.press_entry, collector(self.press_entry, self.entries["press"][0]))
        self.uc.mem_write(self.release_entry, collector(self.release_entry, self.entries["release"][0], True))
        self.uc.mem_write(STOP, bytes.fromhex("4e71"))
        for address in (ON, OFF, KEY):
            self.hooks.append(self.uc.hook_add(UC_HOOK_CODE, self.observe,
                                             begin=address, end=address))
        self.core_call("init", self.tick(), 0)

    def call(self, address, args):
        require(not self.direct, "Nested arp diagnostic transaction")
        context = self.uc.context_save()
        self.direct = True
        try:
            self.uc.reg_write(r.UC_M68K_REG_SR, 0x2700)
            words = [STOP, *(a & 0xFFFFFFFF for a in args)]
            self.uc.mem_write(STACK, struct.pack(">" + "I" * len(words), *words))
            self.uc.reg_write(r.UC_M68K_REG_A7, STACK)
            self.uc.emu_start(address, STOP, count=100_000)
            require(self.uc.reg_read(r.UC_M68K_REG_PC) == STOP,
                    f"Arp native transaction did not return at {address:#x}")
            self.calls += 1
            return self.uc.reg_read(r.UC_M68K_REG_D0)
        finally:
            self.uc.context_restore(context)
            self.direct = False

    def core_call(self, name, *args):
        value = self.call(self.entries[name][0], [STATE, *args])
        require(value != 0xFFFFFFFF, "Native arp rejected an adapter operation")
        return native.commands(self.raw())

    def arm(self):
        # Only call while the CPU worker is paused and keyboard mode is active.
        require(not self.field("owned"), "Arm only with all arp keys released")
        self.core_call("init", self.tick(), int(self.enabled))
        self.collecting = True

    def stock_event(self, event):
        kind, note, velocity = event
        tick = self.tick()
        self.outputs.append({"kind": kind, "note": note, "velocity": velocity,
                             "tick": tick})
        if kind == "on":
            self.call(ON, [0, note, velocity, 0x40, 0, -1, -1, -1, -1])
        else:
            self.call(OFF, [0, note, 0x40, 0])

    def observe(self, uc, pc, size, data):
        sp = uc.reg_read(r.UC_M68K_REG_A7)
        if pc == KEY:
            if self.direct:
                return
            event = self.u32(sp + 8)
            code, flags = self.u32(event + 12), self.u32(event + 16)
            if self.collecting and flags & 1 and not flags & 8:
                if code == 20:
                    self.playing = True
                elif code == 21:
                    self.playing = False
                    self.pending_panic = True
                elif code in (16, 23, 24):
                    self.pending_panic = True
            return
        ret, track, note = self.u32(sp), self.u32(sp + 4), self.u32(sp + 8)
        kind = "on" if pc == ON else "off"
        velocity = self.u32(sp + 12) if pc == ON else 0
        if self.direct or ret not in (PRESS_RETURN, RELEASE_RETURN):
            if not self.direct and ret >= CODE:
                self.outputs.append({"kind": kind, "note": note,
                                     "velocity": velocity, "tick": self.tick()})
            self.stock_calls.append({"kind": kind, "track": track, "note": note,
                                     "velocity": velocity, "tick": self.tick(),
                                     "generated": self.direct or ret >= CODE})
            return
        owner = self.u32(STATE + native.OWNERS + note * 4) if note < 128 else 0
        consume = track == 0 and self.collecting and (
            self.field("enabled") if pc == ON else owner)
        self.inputs.append({"kind": kind, "track": track, "note": note,
                            "velocity": velocity, "tick": self.tick(),
                            "consumed": bool(consume)})
        if consume:
            uc.reg_write(r.UC_M68K_REG_PC,
                         self.press_entry if pc == ON else self.release_entry)
        else:
            self.stock_calls.append({"kind": kind, "track": track, "note": note,
                                     "velocity": velocity, "tick": self.tick(),
                                     "generated": False})

    def service(self):
        if not self.collecting:
            return
        if self.pending_panic:
            for event in self.core_call("panic"):
                self.stock_event(event)
            self.pending_panic = False
        for event in self.core_call("clock", self.tick(), int(self.playing)):
            self.stock_event(event)
