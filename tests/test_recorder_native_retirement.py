"""Execute lease, root, wire and completion-domain checks as ColdFire code."""

import struct
import unittest

from buf_native_support import NativeRetirementFixture, r, u

from lab import recorder_ack as ack
from lab import recorder_ack_loop as loop
from lab import recorder_freeze_code as n
from lab import recorder_freeze_worker_code as q
from lab import recorder_native_retirement as t
from lab import recorder_seat_reuse as seats
from lab import recorder_worker_code as w


@unittest.skipIf(u is None, "Requires configured native CPU runtime")
class NativeRetirementTests(NativeRetirementFixture, unittest.TestCase):
    def test_native_root_validation_latches_exact_entry_extent(self):
        self.assertEqual(self.call(t.VALIDATE), 0)
        self.assertEqual(
            [self.get(t.STATE + x) for x in (t.ENTRY, t.PRIVATE, t.START, t.SIZE)],
            [n.GEN, 304, 9216, 16384],
        )

    def test_native_lease_requires_context_and_empty_inflight_count(self):
        for at in (
            w.STATE + 12,
            q.CURRENT_TCB,
            t.STATE + t.OWNER,
            t.STATE + t.EPOCH,
            t.STATE + t.KIT,
            n.STATE + 24,
            q.STATE + 56,
            q.STOCK_BUSY,
            t.STATE + t.CANCEL,
        ):
            old = self.get(at)
            self.put(at, old + 1)
            self.assertNotEqual(self.call(t.VALIDATE), 0)
            self.put(at, old)

    def test_current_alias_snapshot_and_unsupported_machine_refuse(self):
        self.put(0x405B1368 + 300 * 16, seats.FIRST_ID)
        self.assertEqual(self.call(t.VALIDATE), 0xFFFFFFFB)
        self.put(0x405B1368 + 300 * 16, 0)
        self.put(n.SNAP, 1, n.SNAP_FIRST, 1, 0, seats.FIRST_ID)
        self.assertEqual(self.call(t.VALIDATE), 0xFFFFFFFD)
        self.put(n.SNAP, 0)
        self.cpu.mem_write(0x2040D6, b"\x02")
        self.assertEqual(self.call(t.VALIDATE), 0xFFFFFFFF)

    def test_sealed_lookup_refuses_during_wait_and_recovers_without_free(self):
        self.assertEqual(self.call(t.LOOKUP_GUARD, seats.FIRST_ID), 0)
        self.put(w.STATE + 12, 0)
        self.assertEqual(self.call(t.LOOKUP_GUARD, seats.FIRST_ID), n.GEN)

    def test_driver_rejects_every_private_selection_and_preserves_public_frame(self):
        self.cpu.mem_write(t.RAW_DRIVER, bytes.fromhex("202f00084e75"))
        data = bytearray(0xABC)
        for track in range(16):
            struct.pack_into(">H", data, 0xE0 + track * 0x60, 300)
        self.cpu.mem_write(0x20A000, bytes(data))
        self.assertEqual(
            self.call(t.DRIVER, 0x802, 0x20A000, 0xABC, 0x20B000), 0x20A000
        )
        self.assertEqual(bytes(self.cpu.mem_read(0x20A000, len(data))), bytes(data))
        for slot in range(304, 312):
            for track in (0, 7, 15):
                trial = bytearray(data)
                struct.pack_into(">H", trial, 0xE0 + track * 0x60, slot)
                self.cpu.mem_write(0x20A000, bytes(trial))
                self.assertEqual(
                    self.call(t.DRIVER, 0x802, 0x20A000, 0xABC, 0x20B000), 0xFFFFFFFF
                )
                self.assertEqual(self.get(t.STATE + t.CANCEL), 1)
        self.assertEqual(self.get(t.STATE + 92), 24)

    def test_foreign_and_waiting_worker_cannot_mutate_samples(self):
        for i in range(3):
            self.cpu.mem_write(w.SLOT_GUARDS + i * 256, bytes.fromhex("702a4e75"))
        for phase, owner in ((2, 0x203000), (3, 0x203004)):
            self.put(t.STATE + t.PHASE, phase)
            self.put(t.STATE + t.OWNER, owner)
            for i in range(3):
                self.assertEqual(
                    self.call(t.GUARDS + i * 256, 0, 300), 0xFFFFFFFF if i == 0 else 0
                )
        self.put(t.STATE + t.PHASE, 3)
        self.put(t.STATE + t.OWNER, 0x203000)
        for i in range(3):
            self.assertEqual(
                self.call(t.GUARDS + i * 256, 0, 300),
                0xFFFFFFFF if i == 0 else 0,
            )
        self.put(t.STATE + t.ACTIVE_UNLOAD, 1)
        self.assertEqual(self.call(t.GUARDS, 0, 300), 42)

    def test_shared_worker_job_cannot_borrow_queued_commit_authority(self):
        for i in range(3):
            self.cpu.mem_write(w.SLOT_GUARDS + i * 256, bytes.fromhex("702a4e75"))
        for phase in (1, 2, 3):
            self.put(t.STATE + t.PHASE, phase)
            self.put(t.STATE + t.OWNER, 0x203000)
            self.put(t.STATE + t.ACTIVE_UNLOAD, 0)
            for i in range(3):
                self.assertEqual(
                    self.call(t.GUARDS + i * 256, 0, 300),
                    0xFFFFFFFF if i == 0 else 0,
                )
        self.put(t.STATE + t.ACTIVE_UNLOAD, 1)
        for i in range(3):
            self.assertEqual(self.call(t.GUARDS + i * 256, 0, 300), 42)

    def test_preempted_entry_rechecks_lease_after_acquiring_operation_count(self):
        self.cpu.mem_write(q.ENTER, q.operation_count(q.ENTER, 1))
        self.cpu.mem_write(q.LEAVE, q.operation_count(q.LEAVE, -1))
        self.cpu.mem_write(
            q.GUARDS, q.slot_guard(q.GUARDS, w.SLOT_GUARDS, load=True)
        )
        self.cpu.mem_write(w.SLOT_GUARDS, bytes.fromhex("702a4e75"))
        self.put(w.STATE + 12, 0)

        def admit_retirement(*_):
            self.put(w.STATE + 12, 3)
            self.put(t.STATE + t.PHASE, 2)

        self.cpu.hook_add(
            u.UC_HOOK_CODE, admit_retirement, begin=q.ENTER, end=q.ENTER
        )
        self.assertEqual(self.call(t.GUARDS, 0, 500), 0xFFFFFFFF)
        self.assertEqual(self.get(q.STATE + 56), 0)

    def test_operation_count_covers_legacy_body_and_blocks_new_admission(self):
        self.put(w.STATE + 12, 0)
        self.cpu.mem_write(w.SLOT_GUARDS, bytes.fromhex("702a4e75"))
        seen = []
        self.cpu.hook_add(
            u.UC_HOOK_CODE,
            lambda *_: seen.append(self.get(q.STATE + 56)),
            begin=w.SLOT_GUARDS,
            end=w.SLOT_GUARDS,
        )
        self.assertEqual(self.call(t.GUARDS, 0, 500), 42)
        self.assertEqual(seen, [1])
        self.assertEqual(self.get(q.STATE + 56), 0)
        self.put(q.STATE + 56, 1)
        self.cpu.reg_write(r.UC_M68K_REG_D0, 1)
        self.assertEqual(self.call(t.QUEUE), 0xFFFFFFFF)
        self.assertEqual(self.get(w.STATE + 12), 0)

    def test_existing_freeze_job_gate_is_preserved_inside_counter(self):
        self.put(w.STATE + 12, 2)
        self.put(q.STATE + 8, 2)
        self.put(q.STATE + 20, 1, 0x204000, 0x203000)
        self.put(q.STATE + 48, 1)
        self.cpu.mem_write(w.SLOT_GUARDS, bytes.fromhex("702a4e75"))
        self.assertEqual(self.call(t.GUARDS, 0, 500), 42)
        self.assertEqual(self.get(q.STATE + 56), 0)
        self.put(q.STATE + 48, 0)
        self.assertEqual(self.call(t.GUARDS, 0, 500), 0xFFFFFFFF)
        self.assertEqual(self.get(q.STATE + 56), 0)

    def test_receipt_only_cannot_confirm_retirement_domain(self):
        state = ack.constants()["CF_STATE"]
        words = (1, seats.FIRST_ID, 7, t.contract()["constants"]["RTOK"])
        expected = bytes(
            (i << 2) | ((words[i // 16] >> (2 * (i % 16))) & 3) for i in range(64)
        )
        self.cpu.mem_write(ack.CF_EXPECTED, expected)
        self.put(state + ack.PHASE, 1)
        old = ack.fragments(*words[:3])
        for _ in range(3):
            for b in old:
                self.cpu.mem_write(0x8000488C + 24, bytes([b]))
                self.call(ack.CF_CONSUME)
        self.assertNotEqual(self.get(state + ack.PHASE), 2)
        for b in expected:
            self.cpu.mem_write(0x8000488C + 24, bytes([b]))
            self.call(ack.CF_CONSUME)
        self.assertEqual(self.get(state + ack.PHASE), 2)

    def test_commit_needs_matching_reply_and_unloads_below_ipl7(self):
        self.assertEqual(self.call(t.VALIDATE), 0)
        self.put(t.STATE + t.PHASE, 3)
        self.assertEqual(self.call(t.COMMIT), 0xFFFFFFFF)
        state = ack.constants()["CF_STATE"]
        self.put(state + 4, 1, seats.FIRST_ID, 0, 9216, 16384, 2)
        self.cpu.mem_write(n.UNLOAD, bytes.fromhex("70004e75"))
        self.cpu.mem_write(seats.CLEAN, bytes.fromhex("70004e75"))
        observed = []
        self.cpu.hook_add(
            u.UC_HOOK_CODE,
            lambda cpu, *_: observed.append(
                (cpu.reg_read(r.UC_M68K_REG_SR), self.get(t.STATE + t.ACTIVE_UNLOAD))
            ),
            begin=n.UNLOAD,
            end=n.UNLOAD,
        )
        self.assertEqual(self.call(t.COMMIT), 0)
        self.assertEqual(observed[0][0] & 0x700, 0)
        self.assertEqual(observed[0][1], 1)
        self.assertEqual(self.get(t.STATE + t.ACTIVE_UNLOAD), 0)
        self.assertEqual(self.get(n.GEN), 3)
        self.assertEqual(self.get(t.STATE + t.SUCCESSES), 1)

    def receive(self):
        stack, stop = 0x20F000, 0x20FF00
        self.put(stack, 0, 0, 0, 0, stop)
        self.cpu.mem_write(0x4002DD88, bytes.fromhex("4e75"))
        self.cpu.reg_write(r.UC_M68K_REG_SR, 0x2500)
        self.cpu.reg_write(r.UC_M68K_REG_A7, stack)
        registers = (
            r.UC_M68K_REG_D0,
            r.UC_M68K_REG_D1,
            r.UC_M68K_REG_A0,
            r.UC_M68K_REG_A1,
        )
        for i, register in enumerate(registers):
            self.cpu.reg_write(register, 0x123400 + i)
        self.cpu.emu_start(loop.RECEIVE, stop, count=10000)
        self.assertEqual(self.cpu.reg_read(r.UC_M68K_REG_PC), stop)
        self.assertEqual(self.cpu.reg_read(r.UC_M68K_REG_A7), stack + 20)
        self.assertEqual(
            [self.cpu.reg_read(x) for x in registers],
            [0x123400 + i for i in range(4)],
        )

    def setup_notification(self, phase=2):
        self.put(t.STATE + t.PHASE, 2)
        self.put(ack.constants()["CF_STATE"] + ack.PHASE, phase)
        self.put(0x40966F40, 0)
        self.put(0x40966F4C, 7)
        self.cpu.mem_write(0x40001896, bytes.fromhex("70004e75"))
        posted = []

        def observe(cpu, *_):
            sp = cpu.reg_read(r.UC_M68K_REG_A7)
            posted.append((self.get(sp + 4), self.get(sp + 8)))

        self.cpu.hook_add(
            u.UC_HOOK_CODE, observe, begin=0x40001896, end=0x40001896
        )
        return posted

    def test_native_isr_wakes_gui_once_for_a_confirmed_transaction(self):
        posted = self.setup_notification()
        self.receive()
        self.receive()
        self.assertEqual(posted, [(0x40966F3C, 0x40240EB8)])
        self.assertEqual(self.get(t.STATE + 100), 1)

    def test_native_isr_pending_reply_does_not_wake_without_cancel(self):
        posted = self.setup_notification(phase=1)
        self.receive()
        self.assertEqual(posted, [])
        self.put(t.STATE + t.CANCEL, 1)
        self.receive()
        self.assertEqual(posted, [(0x40966F3C, 0x40240EB8)])

    def test_native_isr_expiry_wakes_and_full_gui_queue_retries(self):
        posted = self.setup_notification(phase=3)
        self.put(0x40966F40, 8)
        self.receive()
        self.assertEqual(posted, [])
        self.assertEqual(self.get(t.STATE + 100), 0)
        self.put(0x40966F40, 7)
        self.receive()
        self.assertEqual(posted, [(0x40966F3C, 0x40240EB8)])

    def test_poll_cancellation_unlocks_without_tombstone_or_free(self):
        self.put(t.STATE + t.PHASE, 2)
        self.put(t.STATE + t.CANCEL, 1)
        self.cpu.mem_write(q.POLL, bytes.fromhex("4e75"))
        before = bytes(self.cpu.mem_read(n.GEN, 64))
        self.call(t.POLL)
        self.assertEqual(self.get(t.STATE + t.PHASE), 5)
        self.assertEqual(self.get(t.STATE + 12), 0xFFFFFFFA)
        self.assertEqual(self.get(w.STATE + 12), 0)
        self.assertEqual(bytes(self.cpu.mem_read(n.GEN, 64)), before)

    def test_commit_revalidates_each_exact_acknowledged_field(self):
        self.assertEqual(self.call(t.VALIDATE), 0)
        self.put(t.STATE + t.PHASE, 3)
        state = ack.constants()["CF_STATE"]
        self.put(state + 4, 1, seats.FIRST_ID, 0, 9216, 16384, 2)
        for off in (ack.EPOCH, ack.GENERATION, ack.SEQUENCE, ack.START, ack.SIZE):
            original = self.get(state + off)
            self.put(state + off, original + 1)
            self.assertEqual(self.call(t.COMMIT), 0xFFFFFFFF)
            self.assertEqual(self.get(n.GEN), 1)
            self.assertEqual(self.get(t.STATE + t.SUCCESSES), 0)
            self.put(state + off, original)

    def test_context_switch_after_scan_cannot_cross_atomic_tombstone(self):
        self.assertEqual(self.call(t.VALIDATE), 0)
        self.put(t.STATE + t.PHASE, 3)
        state = ack.constants()["CF_STATE"]
        self.put(state + 4, 1, seats.FIRST_ID, 0, 9216, 16384, 2)
        atomic = t.COMMIT + t.commit().index(bytes.fromhex("40c72007"))
        for address in (
            n.STATE,
            0x80004704,
            q.CURRENT_TCB,
            q.STATE + 56,
            w.STATE + 12,
            t.STATE + t.PHASE,
            t.STATE + t.CANCEL,
        ):
            old = self.get(address)

            def change(*_, at=address, value=old):
                self.put(at, value + 1)

            hook = self.cpu.hook_add(
                u.UC_HOOK_CODE, change, begin=atomic, end=atomic
            )
            self.assertEqual(self.call(t.COMMIT), 0xFFFFFFFF)
            self.cpu.hook_del(hook)
            self.assertEqual(self.get(n.GEN), 1)
            self.assertEqual(self.get(t.STATE + t.SUCCESSES), 0)
            self.assertEqual(self.cpu.reg_read(r.UC_M68K_REG_SR) & 0x700, 0)
            self.put(address, old)

    def test_machine_switch_after_scan_cannot_cross_atomic_tombstone(self):
        self.assertEqual(self.call(t.VALIDATE), 0)
        self.put(t.STATE + t.PHASE, 3)
        state = ack.constants()["CF_STATE"]
        self.put(state + 4, 1, seats.FIRST_ID, 0, 9216, 16384, 2)
        atomic = t.COMMIT + t.commit().index(bytes.fromhex("40c72007"))
        self.cpu.hook_add(
            u.UC_HOOK_CODE,
            lambda *_: self.cpu.mem_write(0x2040D6, b"\x02"),
            begin=atomic,
            end=atomic,
        )
        self.assertEqual(self.call(t.COMMIT), 0xFFFFFFFF)
        self.assertEqual(self.get(n.GEN), 1)

    def test_second_input_cannot_replace_a_waiting_transaction(self):
        self.put(t.STATE + t.PHASE, 2)
        self.put(ack.constants()["CF_STATE"] + ack.PHASE, 1)
        self.put(t.STATE, 1, 0)
        self.put(t.STATE + 16, seats.FIRST_ID + 1)
        self.cpu.mem_write(q.POLL, bytes.fromhex("4e75"))
        fields = (t.PHASE, t.TOKEN, t.EPOCH, t.KIT, t.OWNER, t.SEQ)
        before = [self.get(t.STATE + x) for x in fields]
        self.call(t.POLL)
        self.assertEqual([self.get(t.STATE + x) for x in fields], before)
        self.assertEqual(self.get(t.STATE + 4), 1)
        self.assertEqual(self.get(t.STATE + 96), 1)
        self.assertEqual(self.get(w.STATE + 12), 3)

    def test_native_timeout_retains_entry_and_unlocks_admission(self):
        state = ack.constants()["CF_STATE"]
        self.put(state + ack.PHASE, 1)
        self.put(t.STATE + t.PHASE, 2)
        self.cpu.mem_write(q.POLL, bytes.fromhex("4e75"))
        before = bytes(self.cpu.mem_read(n.GEN, 64))
        for _ in range(511):
            self.call(ack.CF_CONSUME)
        self.assertEqual(self.get(state + ack.PHASE), 1)
        self.assertEqual(self.call(ack.CF_CONSUME), 0xFFFFFFFF)
        self.assertEqual(self.get(state + ack.TIMEOUTS), 1)
        self.call(t.POLL)
        self.assertEqual(self.get(t.STATE + t.PHASE), 5)
        self.assertEqual(self.get(t.STATE + 12), 0xFFFFFFFA)
        self.assertEqual(self.get(w.STATE + 12), 0)
        self.assertEqual(bytes(self.cpu.mem_read(n.GEN, 64)), before)

    def test_prepare_callback_keeps_lease_until_commit_or_failure(self):
        self.put(t.STATE + 72, 1)
        self.call(t.DONE, 0, 0)
        self.assertEqual(self.get(t.STATE + t.PHASE), 2)
        self.assertEqual(self.get(w.STATE + 12), 3)
        self.call(t.DONE, 0, 0xFFFFFFFF)
        self.assertEqual(self.get(t.STATE + t.PHASE), 5)
        self.assertEqual(self.get(w.STATE + 12), 0)
        self.assertEqual(self.get(n.GEN), 1)

    def test_unknown_driver_transaction_cancels_only_while_leased(self):
        self.cpu.mem_write(t.RAW_DRIVER, bytes.fromhex("202f00084e75"))
        self.assertEqual(self.call(t.DRIVER, 4, 0x20A000, 0, 0), 0xFFFFFFFF)
        self.assertEqual(self.get(t.STATE + t.CANCEL), 1)
        self.put(w.STATE + 12, 0)
        self.assertEqual(self.call(t.DRIVER, 4, 0x20A000, 0, 0), 0x20A000)

    def test_aliases_in_either_cpu_pool_and_last_track_machine_refuse(self):
        for at in (0x405B1368 + 400 * 16, 0x209000 + 400 * 16):
            self.put(at, seats.FIRST_ID)
            self.assertEqual(self.call(t.VALIDATE), 0xFFFFFFFB)
            self.put(at, 0)
        self.cpu.mem_write(0x204000 + 15 * 0x450 + 0xD6, b"\x02")
        self.assertEqual(self.call(t.VALIDATE), 0xFFFFFFFF)
