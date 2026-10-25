"""Fresh CFV4E execution of the four-mode core; never reuse translated UP code."""
import unicorn as u
from unicorn import m68k_const as r

from lab import arp_modes as native
from lab.arp_emulation import CODE, STATE, STOP, NativeCore


class ModesCore(NativeCore):
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
        return int.from_bytes(self.cpu.mem_read(STATE + native.FIELDS[name], 4), "big")
