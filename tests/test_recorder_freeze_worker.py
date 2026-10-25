"""Native queue ownership, small-function ABI and fail-closed lifetime limits."""

import struct
import unittest

from lab import recorder_freeze_code as n
from lab import recorder_freeze_worker_code as q
from lab import recorder_worker_code as w
from lab.emit import Code

try:
    import unicorn as u
    from unicorn import m68k_const as r
except ImportError:
    u = None


@unittest.skipIf(u is None, "Requires configured ColdFire runtime")
class FreezeWorkerTests(unittest.TestCase):
    def setUp(self):
        self.cpu = u.Uc(u.UC_ARCH_M68K, u.UC_MODE_BIG_ENDIAN)
        self.cpu.ctl_set_cpu_model(r.UC_CPU_M68K_CFV4E)
        for at, length in (
            (q.BASE, q.END - q.BASE),
            (w.BASE, w.END - w.BASE),
            (n.BASE, 0x8000),
            (0x10300000, 0x1000),
            (0x47DB3000, 0x1000),
            (0x405B1000, 0x1000),
            (0x80004000, 0x1000),
            (0x200000, 0x10000),
        ):
            self.cpu.mem_map(at, length)
        for at, data in {**w.payload(), **q.payload()}.items():
            self.cpu.mem_write(at, data)
        self.stack, self.stop = 0x20F000, 0x20FF00

    def put(self, at, *values):
        self.cpu.mem_write(at, struct.pack(">" + "I" * len(values), *values))

    def get(self, at):
        return struct.unpack(">I", self.cpu.mem_read(at, 4))[0]

    def call(self, at, *args):
        self.put(self.stack, self.stop, *args)
        self.cpu.reg_write(r.UC_M68K_REG_SR, 0x2000)
        self.cpu.reg_write(r.UC_M68K_REG_A7, self.stack)
        self.cpu.emu_start(at, self.stop, count=10000)
        self.assertEqual(self.cpu.reg_read(r.UC_M68K_REG_PC), self.stop)
        self.assertEqual(self.cpu.reg_read(r.UC_M68K_REG_A7), self.stack + 4)
        return self.cpu.reg_read(r.UC_M68K_REG_D0)

    def owned(self):
        self.put(w.STATE + 12, 2)
        self.put(q.STATE + 8, 2)
        self.put(q.STATE + 48, 1)
        self.put(q.STATE + 28, 0x204000)
        self.put(q.CURRENT_TCB, 0x204000)
        self.put(n.STATE, 1)
        self.put(q.STATE + 20, 1, 0x205000)
        self.put(0x80004704, 0x205000)

    def test_gate_requires_live_task_lease_epoch_and_kit(self):
        self.owned()
        self.assertEqual(self.call(q.GATE), 0)
        for at in (
            q.STATE + 48,
            q.STATE + 8,
            q.STATE + 28,
            q.CURRENT_TCB,
            q.STATE + 20,
            q.STATE + 24,
        ):
            old = self.get(at)
            self.put(at, old + 1)
            self.assertEqual(self.call(q.GATE), 0xFFFFFFFF)
            self.put(at, old)

    def test_cross_task_sample_mutations_are_denied(self):
        self.owned()
        self.put(q.CURRENT_TCB, 0x206000)
        for i in range(3):
            self.cpu.mem_write(w.SLOT_GUARDS + i * 256, bytes.fromhex("702a4e75"))
            self.assertEqual(
                self.call(q.GUARDS + i * 256, 0, 300), 0xFFFFFFFF if i == 0 else 0
            )
            self.assertEqual(self.get(q.STATE + 56), 0)
        self.put(q.CURRENT_TCB, 0x204000)
        self.assertEqual(self.call(q.GUARDS, 0, 300), 42)

    def test_inflight_operation_refuses_admission_and_worker_before_body(self):
        self.put(q.STATE + 56, 1)
        self.assertEqual(self.call(q.SUBMIT), 0xFFFFFFF9)
        self.put(w.STATE + 12, 2)
        self.put(q.STATE + 8, 1)
        self.assertEqual(self.call(q.WORKER), 0xFFFFFFFF)
        self.assertEqual(self.get(q.STATE + 56), 1)
        self.assertEqual(self.get(q.STATE + 48), 0)

    def test_counter_restores_interrupt_mask_and_nested_depth(self):
        self.call(q.ENTER)
        self.call(q.ENTER)
        self.assertEqual(self.get(q.STATE + 56), 2)
        self.call(q.LEAVE)
        self.call(q.LEAVE)
        self.assertEqual(self.get(q.STATE + 56), 0)
        self.assertEqual(self.cpu.reg_read(r.UC_M68K_REG_SR) & 0x2700, 0x2000)

    def test_operation_diagnostic_preserves_nested_count_arguments_and_outer_lifetime(
        self,
    ):
        self.cpu.mem_map(0x40966000, 4096)
        for at, code in q.payload(operation_diagnostics=True).items():
            self.cpu.mem_write(at, code)
        self.put(q.CURRENT_TCB, 0x206000)
        self.put(0x40966500, 12345)
        c = Code()
        c.emit("2f2f0008")
        n.call(c, q.GUARDS + 0x100, 4)
        for source, target in ((q.OP_RETURNED, 0x200100), (56, 0x200104)):
            c.imm("2039", q.STATE + source)
            c.imm("23c0", target)
        c.emit("702a 4e75")
        self.cpu.mem_write(w.SLOT_GUARDS, c.finish(w.SLOT_GUARDS))
        self.cpu.mem_write(w.SLOT_GUARDS + 0x100, bytes.fromhex("202f00044e75"))
        self.cpu.ctl_remove_cache(q.BASE, q.END)
        self.assertEqual(self.call(q.GUARDS, 0x204000, 300), 42)
        self.assertEqual(self.get(0x200100), 0)  # Nested return did not end outer.
        self.assertEqual(self.get(0x200104), 1)
        self.assertEqual(self.get(q.STATE + 56), 0)
        self.assertEqual(self.get(q.STATE + q.OP_RETURNED), 1)
        for field, expected in (
            (q.OP_SITE, q.GUARDS + 14),
            (q.OP_CALLER, self.stop),
            (q.OP_ARG1, 0x204000),
            (q.OP_ARG2, 300),
            (q.OP_TASK, 0x206000),
            (q.OP_TICK, 12345),
            (q.OP_ENTERS, 2),
            (q.OP_EXITS, 2),
            (q.OP_SERIAL, 1),
        ):
            self.assertEqual(self.get(q.STATE + field), expected)
        self.assertEqual(self.cpu.reg_read(r.UC_M68K_REG_SR) & 0x2700, 0x2000)

    def test_stock_sample_call_argument_order_survives_wrapper(self):
        self.cpu.mem_write(w.SLOT_GUARDS, bytes.fromhex("202f00084e75"))
        self.assertEqual(self.call(q.GUARDS, 0x204000, 300), 300)
        self.assertEqual(self.get(q.STATE + 56), 0)

    def test_normal_and_empty_buffer_requests_fail_before_any_alias(self):
        self.assertEqual(self.call(q.SUBMIT), 0xFFFFFFFF)
        self.owned()
        self.assertEqual(self.call(q.BODY, 1, 1, 0x205000), 0xFFFFFFFE)

    def test_busy_requests_do_not_clobber_context_or_allocate(self):
        self.owned()
        before = bytes(self.cpu.mem_read(q.STATE + 8, 32))
        for _ in range(256):
            self.assertEqual(self.call(q.SUBMIT), 0xFFFFFFF9)
        self.assertEqual(bytes(self.cpu.mem_read(q.STATE + 8, 32)), before)
        self.assertEqual(self.get(q.STATE + 44), 256)
        self.assertEqual(self.get(w.STATE + 12), 2)

    def test_small_function_copy_and_destroy(self):
        self.put(0x204000, q.STATE, 0)
        self.put(0x205000, 0, 0)
        self.assertEqual(self.call(q.MANAGER, 0x205000, 0x204000, 2), 0)
        self.assertEqual(self.get(0x205000), q.STATE)
        self.assertEqual(self.call(q.MANAGER, 0x205000, 0x204000, 3), 0)
        self.assertEqual(self.get(0x204000), q.STATE)

    def test_done_releases_only_shared_job_ownership(self):
        self.owned()
        self.assertEqual(self.call(q.DONE, 0, 312), 0)
        self.assertEqual(self.get(q.STATE + 12), 312)
        self.assertEqual(self.get(q.STATE + 8), 3)
        self.assertEqual(self.get(q.STATE + 32), 1)
        self.assertEqual(self.get(w.STATE + 12), 0)
        self.assertEqual(self.get(q.STATE + 48), 0)

    def test_no_unleased_or_masked_bypass_into_worker_body(self):
        self.assertEqual(self.call(q.BODY, 1, 1, 0), 0xFFFFFFFF)

    def test_recorder_full_capacity_remains_bounded_without_reader_ack(self):
        self.put(w.STATE + 12, 1)
        self.put(w.STATE + 60, 1)
        self.put(n.STATE, 1)
        self.put(w.STATE + 44, 0x204000)
        self.put(0x80004704, 0x204000)
        self.put(w.STATE + 4, 8)
        before = bytes(self.cpu.mem_read(w.STATE, 192))
        for _ in range(256):
            self.assertEqual(self.call(w.WORKER), 0xFFFFFFFF)
        self.assertEqual(bytes(self.cpu.mem_read(w.STATE, 192)), before)
