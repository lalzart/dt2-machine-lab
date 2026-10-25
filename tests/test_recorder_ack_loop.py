"""Execute the new CF thunks; independently check native metadata/ISR ABI."""

import struct
import unittest

from lab import recorder_ack as ack
from lab import recorder_ack_loop as loop
from lab import recorder_retirement as obs
from lab import recorder_worker_code as w

try:
    import unicorn as u
    from unicorn import m68k_const as k
except ImportError:
    u = None


@unittest.skipIf(u is None, "Requires configured ColdFire runtime")
class ControlPathTests(unittest.TestCase):
    def setUp(self):
        self.c = u.Uc(u.UC_ARCH_M68K, u.UC_MODE_BIG_ENDIAN)
        self.c.ctl_set_cpu_model(k.UC_CPU_M68K_CFV4E)
        for at, size in (
            (0x200000, 65536),
            (obs.CF_BASE, 8192),
            (ack.constants()["CF_BASE"], 16384),
            (loop.BASE, 16384),
            (w.BASE, 0xB000),
            (0x405A0000, 0x20000),
            (0x400CD000, 4096),
            (0x4002D000, 4096),
            (0x80004000, 8192),
        ):
            self.c.mem_map(at, size)
        self.c.mem_write(obs.CF_ENTRY, obs.sender())
        for at, code in (ack.cpu() | loop.cpu()).items():
            self.c.mem_write(at, code)
        self.c.reg_write(k.UC_M68K_REG_SR, 0x2000)
        self.calls = []
        self.private_writes = []

        def private_write(c, _access, address, size, value, _data):
            # At any instruction boundary an ISR must see matching disabled
            # while a new tuple or its expected fragments are being changed.
            self.assertEqual(self.word(ack.constants()["CF_STATE"] + ack.PHASE), 0)
            self.private_writes.append((address, size, value))

        for first, last in (
            (ack.constants()["CF_STATE"] + 4, ack.constants()["CF_STATE"] + 23),
            (ack.CF_EXPECTED, ack.CF_EXPECTED + 47),
        ):
            self.c.hook_add(u.UC_HOOK_MEM_WRITE, private_write, begin=first, end=last)

        def publisher(c, *_):
            sp = c.reg_read(k.UC_M68K_REG_A7)
            ret, tag, ptr, order = struct.unpack(">4I", c.mem_read(sp, 16))
            self.calls.append((tag, order, bytes(c.mem_read(ptr, 4096))))
            if tag == obs.constants()["TAG"]:
                self.assertEqual(self.word(ack.constants()["CF_STATE"] + ack.PHASE), 0)
            c.reg_write(k.UC_M68K_REG_A7, sp + 4)
            c.reg_write(k.UC_M68K_REG_PC, ret)

        self.c.hook_add(u.UC_HOOK_CODE, publisher, begin=0x400CD638, end=0x400CD638)

    def put(self, at, *words):
        self.c.mem_write(at, struct.pack(">" + "I" * len(words), *words))

    def word(self, at):
        return int.from_bytes(self.c.mem_read(at, 4), "big")

    def test_submit_uses_native_allocator_extent_and_preserves_callee_registers(self):
        self.put(w.STATE + 72, 305)
        self.put(0x405B5368 + 305 * 4, 3)
        self.put(0x405A0F64, 0x405A1000)
        self.put(0x405A1000 + 3 * 52 + 16, 0x6400, 0x4000)
        self.put(w.STATE + 60, 7)
        self.put(w.STATE + 20, 0x405A2000)
        self.put(0x405A2004, 0x7FFE0002)
        stack, stop = 0x20F000, 0x20FF00
        regs = (
            k.UC_M68K_REG_D2,
            k.UC_M68K_REG_D3,
            k.UC_M68K_REG_D4,
            k.UC_M68K_REG_A2,
            k.UC_M68K_REG_A3,
        )
        for i, r in enumerate(regs):
            self.c.reg_write(r, 0x123400 + i)
        for sequence in (1, 2):
            self.put(stack, stop)
            self.c.reg_write(k.UC_M68K_REG_A7, stack)
            self.c.emu_start(loop.SUBMIT, stop, count=50000)
            self.assertEqual(self.c.reg_read(k.UC_M68K_REG_PC), stop)
            self.assertEqual(self.c.reg_read(k.UC_M68K_REG_A7), stack + 4)
            for i, r in enumerate(regs):
                self.assertEqual(self.c.reg_read(r), 0x123400 + i)
            self.assertEqual(
                self.calls[-1],
                (
                    obs.constants()["TAG"],
                    1,
                    obs.packet(7, 0x7FFE0002, sequence, 0x6400, 0x4000),
                ),
            )
            self.assertEqual(self.word(loop.STATE + 4), sequence)
            self.assertEqual(self.word(ack.constants()["CF_STATE"] + ack.PHASE), 1)
        self.assertEqual(
            [x[0] for x in self.calls], [0xFFFFFFFF, obs.constants()["TAG"]] * 2
        )
        self.assertEqual(len(self.private_writes), 2 * (5 + 48))

    def test_isr_return_pops_original_arguments_and_preserves_live_registers(self):
        stack = 0x20F000
        stop = 0x4002DD88
        self.put(stack, 1, 2, 3, 4, 0xABCDEF)
        self.c.reg_write(k.UC_M68K_REG_A7, stack)
        regs = (
            k.UC_M68K_REG_D0,
            k.UC_M68K_REG_D1,
            k.UC_M68K_REG_D2,
            k.UC_M68K_REG_D3,
            k.UC_M68K_REG_A0,
            k.UC_M68K_REG_A1,
            k.UC_M68K_REG_A2,
            k.UC_M68K_REG_A3,
        )
        for i, r in enumerate(regs):
            self.c.reg_write(r, 0x123400 + i)
        self.c.emu_start(loop.RECEIVE, stop, count=5000)
        self.assertEqual(self.c.reg_read(k.UC_M68K_REG_PC), stop)
        self.assertEqual(self.c.reg_read(k.UC_M68K_REG_A7), stack + 16)
        for i, r in enumerate(regs):
            self.assertEqual(self.c.reg_read(r), 0x123400 + i)
        self.assertEqual(self.word(loop.STATE + 12), 1)
        self.assertEqual(self.word(ack.constants()["CF_STATE"] + ack.PHASE), 0)
