"""Bounded instruction execution for the original native UP control core."""
import struct

import unicorn as u
from unicorn import m68k_const as r

from lab import arp_native as native

CODE = 0x60000000
STATE = CODE + 0x2000
STACK = CODE + 0xF000
STOP = CODE + 0xFFE0
PRESERVE = tuple(getattr(r, "UC_M68K_REG_" + name)
                 for name in ("D2", "D3", "D4", "D5", "D6", "D7",
                              "A2", "A3", "A4", "A5", "A6"))


class NativeCore:
    def __init__(self, tick=0, enabled=1):
        self.cpu = u.Uc(u.UC_ARCH_M68K, u.UC_MODE_BIG_ENDIAN)
        self.cpu.ctl_set_cpu_model(r.UC_CPU_M68K_CFV4E)
        self.cpu.mem_map(CODE, 0x10000)
        self.entries = native.build(CODE)
        for address, code in self.entries.values():
            self.cpu.mem_write(address, code)
        self.cpu.mem_write(STOP, bytes.fromhex("4e71"))
        self.cpu.reg_write(r.UC_M68K_REG_SR, 0x2700)
        self.call("init", tick, enabled)

    def raw(self):
        return bytes(self.cpu.mem_read(STATE, native.SIZE))

    def field(self, name):
        return struct.unpack_from(">I", self.raw(), native.FIELDS[name])[0]

    def call(self, name, *args):
        cpu = self.cpu
        values = [STOP, STATE, *(a & 0xFFFFFFFF for a in args)]
        cpu.mem_write(STACK, struct.pack(">" + "I" * len(values), *values))
        cpu.reg_write(r.UC_M68K_REG_A7, STACK)
        for reg in PRESERVE:
            cpu.reg_write(reg, 0xBAD000 + reg)
        cpu.emu_start(self.entries[name][0], STOP, count=20_000)
        if cpu.reg_read(r.UC_M68K_REG_PC) != STOP:
            raise RuntimeError("Native arp call exceeded its instruction bound")
        if cpu.reg_read(r.UC_M68K_REG_A7) != STACK + 4:
            raise RuntimeError("Native arp stack ABI changed")
        if any(cpu.reg_read(reg) != 0xBAD000 + reg for reg in PRESERVE):
            raise RuntimeError("Native arp clobbered a nonvolatile register")
        value = cpu.reg_read(r.UC_M68K_REG_D0)
        return value, [] if value == 0xFFFFFFFF else native.commands(self.raw())
